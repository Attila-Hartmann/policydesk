"""The question flow as a LangGraph graph: retrieve → generate, or retrieve → no_context when nothing is relevant.

The graph is compiled once at startup. Its dependencies are bound in closures and are read-only (the semaphore is
concurrency-safe by design); everything about one request lives in the state passed to `ainvoke`. Nodes don't catch
domain errors: they propagate to the API, which maps them to the error contract in one place."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from policydesk.errors import Overloaded
from policydesk.logs import log_event
from policydesk.ports import ChatModel, Embedder
from policydesk.prompts import NO_CONTEXT_ANSWER, SYSTEM_PROMPT, cited_numbers, user_prompt
from policydesk.store import Hit, VectorIndex

logger = logging.getLogger(__name__)

Outcome = Literal["answered", "no_relevant_context"]
OVERLOADED_RETRY_AFTER_SECONDS = 10


class RagState(TypedDict, total=False):
    question: str
    hits: list[Hit]
    answer: str
    outcome: Outcome
    cited: set[int]
    model: str | None


class ModelSlots:
    """Caps concurrent chat calls in this process. Waiting longer than `wait_seconds` for a slot fails fast with
    503 overloaded instead of queueing until every request times out (ADR-005)."""

    def __init__(self, size: int, wait_seconds: float) -> None:
        self._semaphore = asyncio.Semaphore(size)
        self._wait_seconds = wait_seconds

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        try:
            async with asyncio.timeout(self._wait_seconds):
                await self._semaphore.acquire()
        except TimeoutError:
            raise Overloaded(
                "All model slots are busy. Please retry shortly.", retry_after=OVERLOADED_RETRY_AFTER_SECONDS
            ) from None
        try:
            yield
        finally:
            self._semaphore.release()


def build_graph(
    embedder: Embedder, chat: ChatModel, index: VectorIndex, slots: ModelSlots, *, top_k: int, min_score: float
) -> CompiledStateGraph[RagState, None, RagState, RagState]:
    async def retrieve(state: RagState) -> RagState:
        start = time.perf_counter()
        [vector] = await embedder.embed([state["question"]])
        hits = index.search(vector, top_k=top_k, min_score=min_score)
        log_event(
            logger,
            "retrieval",
            hits=len(hits),
            top_score=hits[0].score if hits else None,
            ms=_ms(start),
            question_chars=len(state["question"]),
        )
        return {"hits": hits}

    def route(state: RagState) -> Literal["generate", "no_context"]:
        return "generate" if state["hits"] else "no_context"

    async def generate(state: RagState) -> RagState:
        hits = state["hits"]
        queued = time.perf_counter()
        async with slots.slot():
            start = time.perf_counter()
            completion = await chat.complete(SYSTEM_PROMPT, user_prompt(state["question"], hits))
        cited = cited_numbers(completion.text, len(hits))
        log_event(
            logger,
            "generation",
            model=chat.model,
            queue_ms=round((start - queued) * 1000),
            ms=_ms(start),
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            cited=len(cited),
            answer_chars=len(completion.text),
        )
        return {"answer": completion.text, "outcome": "answered", "cited": cited, "model": chat.model}

    def no_context(state: RagState) -> RagState:
        log_event(logger, "no_relevant_context", min_score=min_score)
        return {"answer": NO_CONTEXT_ANSWER, "outcome": "no_relevant_context", "cited": set(), "model": None}

    graph = StateGraph(RagState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_node("no_context", no_context)
    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges("retrieve", route, ["generate", "no_context"])
    graph.add_edge("generate", END)
    graph.add_edge("no_context", END)
    return graph.compile()


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)
