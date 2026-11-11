import asyncio
import io
import json
import logging
import re
import zlib
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from policydesk.api import create_app
from policydesk.config import Settings
from policydesk.ingest import ingest
from policydesk.logs import JsonFormatter
from policydesk.ports import Completion

DIMS = 256
_STOPWORDS = {"the", "a", "an", "in", "is", "of", "per", "what", "how", "much", "do", "i", "for", "and", "to"}

TRAVEL = """# Travel Policy

Owner: Finance

## Meal allowance

The daily meal allowance in Vienna is EUR 45.

## Hotels

The hotel cap in London is GBP 220 per night.
"""

LEAVE = """# Leave Policy

## Annual leave

Employees receive 25 days of annual leave per year.
"""


def bag_of_words(text: str) -> list[float]:
    """Deterministic toy embedding: hashed word counts. Shared words → high cosine, unrelated words → 0."""
    vector = [0.0] * DIMS
    for word in re.findall(r"\w+", text.lower()):
        if word not in _STOPWORDS:
            vector[zlib.crc32(word.encode()) % DIMS] += 1.0
    return vector


class FakeEmbedder:
    def __init__(self, model: str = "fake-embed") -> None:
        self.model = model
        self.calls = 0
        self.error: Exception | None = None

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        if self.error:
            raise self.error
        return [bag_of_words(t) for t in texts]


class FakeChat:
    """Echoes the question and cites excerpt [1]. Delay and error can be scripted per test."""

    model = "fake-chat"

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.delay: Callable[[str], float] = lambda question: 0.0
        self.error: Exception | None = None
        self.reply: str | None = None

    async def complete(self, system: str, user: str) -> Completion:
        self.prompts.append(user)
        question = user.rsplit("Question: ", 1)[1]
        await asyncio.sleep(self.delay(question))
        if self.error:
            raise self.error
        return Completion(self.reply or f"Answer to: {question} [1]", prompt_tokens=100, completion_tokens=10)


@pytest.fixture
def docs_dir(tmp_path: Path) -> Path:
    path = tmp_path / "docs"
    path.mkdir()
    (path / "travel.md").write_text(TRAVEL, encoding="utf-8")
    (path / "leave.md").write_text(LEAVE, encoding="utf-8")
    return path


@pytest.fixture
def settings_factory(tmp_path: Path, docs_dir: Path) -> Callable[..., Settings]:
    def make(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "docs_dir": docs_dir,
            "index_path": tmp_path / "var" / "index.json",
            "base_url": "http://model.invalid/v1",
            "chat_model": "fake-chat",
            "embedding_model": "fake-embed",
            "min_relevance_score": 0.3,
            "top_k": 3,
            "request_timeout_seconds": 5,
            "llm_max_retries": 0,
            "max_concurrent_model_calls": 4,
            "queue_timeout_seconds": 1,
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)  # type: ignore[call-arg]

    return make


@pytest.fixture
def chat() -> FakeChat:
    return FakeChat()


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def make_client(
    settings_factory: Callable[..., Settings], chat: FakeChat, embedder: FakeEmbedder
) -> Iterator[Callable[..., TestClient]]:
    """Builds the index with the fake embedder, then starts the app with the fakes and the given setting overrides."""
    clients: list[TestClient] = []

    def make(**overrides: Any) -> TestClient:
        settings = settings_factory(**overrides)
        asyncio.run(ingest(settings.docs_dir, settings.index_path, FakeEmbedder()))
        client = TestClient(create_app(settings, chat=chat, embedder=embedder))
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()


@pytest.fixture
def json_logs() -> Iterator[Callable[[], list[dict[str, Any]]]]:
    """Captures log lines exactly as production formats them (the request id is read at emit time)."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    root.removeHandler(handler)
    root.setLevel(old_level)
