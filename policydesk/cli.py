"""Command line: `serve` (ingest + model check + API), `ingest`, and `search` (retrieval scores only,
for threshold calibration)."""

import argparse
import asyncio
import logging

import uvicorn

from policydesk.api import create_app
from policydesk.config import Settings, load_settings
from policydesk.errors import PolicydeskError, StartupError
from policydesk.ingest import ingest
from policydesk.logs import log_event, setup_logging
from policydesk.providers import OpenAICompatibleChat, OpenAICompatibleEmbedder, make_client
from policydesk.store import VectorIndex

logger = logging.getLogger("policydesk.cli")

STARTUP_TIMEOUT_SECONDS = 300


async def prepare(settings: Settings, *, check_models: bool) -> VectorIndex:
    """Build the index if needed and, for `serve`, prove both models answer before any traffic is accepted.
    In local mode the check also loads the models into memory, so the first question doesn't pay for it.
    Startup gets its own generous timeout: a cold model load is not a user request."""
    client = make_client(settings.model_copy(update={"request_timeout_seconds": STARTUP_TIMEOUT_SECONDS}))
    try:
        embedder = OpenAICompatibleEmbedder(client, settings.embedding_model)
        try:
            index, _ = await ingest(settings.docs_dir, settings.index_path, embedder)
            if check_models:
                await embedder.embed(["ping"])
                chat = OpenAICompatibleChat(client, settings.chat_model, settings.reasoning_effort)
                await chat.complete("Reply with the single word OK.", "ping")
                log_event(logger, "model_check_ok", chat_model=settings.chat_model)
        except PolicydeskError as e:
            raise StartupError(
                f"Model check failed against {settings.base_url} (chat model '{settings.chat_model}', "
                f"embedding model '{settings.embedding_model}'): {e.message} Check BASE_URL, API_KEY and the model "
                "names; in local mode, check that the models are pulled."
            ) from e
        return index
    finally:
        await client.close()


async def search(settings: Settings, question: str) -> None:
    client = make_client(settings)
    try:
        index = VectorIndex.load(settings.index_path, settings.embedding_model)
        [vector] = await OpenAICompatibleEmbedder(client, settings.embedding_model).embed([question])
    finally:
        await client.close()
    print(f"threshold MIN_RELEVANCE_SCORE={settings.min_relevance_score}")
    for hit in index.search(vector, top_k=settings.top_k, min_score=-1.0):
        mark = "PASS" if hit.score >= settings.min_relevance_score else "    "
        print(f"{hit.score:.4f} {mark} {hit.chunk.id:32} {hit.chunk.section}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m policydesk")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="build the index if needed, check the models, start the API")
    commands.add_parser("ingest", help="build the index from DOCS_DIR (skipped if already up to date)")
    search_cmd = commands.add_parser("search", help="print retrieval scores for a question (no chat model call)")
    search_cmd.add_argument("question")
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
        setup_logging(settings.log_level)
        if args.command == "search":
            asyncio.run(search(settings, args.question))
            return 0
        asyncio.run(prepare(settings, check_models=args.command == "serve"))
        if args.command == "serve":
            # One worker on purpose: requests mostly wait on the model, and more workers would multiply the
            # per-process model-call cap and the in-memory index.
            uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_config=None, access_log=False)
        return 0
    except StartupError as e:
        setup_logging("INFO")
        log_event(logger, "startup_failed", logging.ERROR, reason=str(e))
        return 1
