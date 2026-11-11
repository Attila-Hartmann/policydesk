"""Application logic: run the question flow under one deadline and shape the result."""

import asyncio
from typing import cast

from langgraph.graph.state import CompiledStateGraph

from policydesk.errors import ModelTimeout
from policydesk.graph import RagState
from policydesk.schemas import Answer, Source


class AskService:
    def __init__(
        self, graph: CompiledStateGraph[RagState, None, RagState, RagState], request_timeout_seconds: float
    ) -> None:
        self._graph = graph
        self._timeout = request_timeout_seconds

    async def ask(self, question: str) -> Answer:
        try:
            async with asyncio.timeout(self._timeout):
                state = cast(RagState, await self._graph.ainvoke({"question": question}))
        except TimeoutError:
            raise ModelTimeout(f"No answer within the {self._timeout:g} s request deadline.") from None

        hits = state.get("hits", [])
        cited = state.get("cited", set())
        return Answer(
            outcome=state["outcome"],
            answer=state["answer"],
            sources=[
                Source(
                    chunk_id=hit.chunk.id,
                    document=hit.chunk.document,
                    title=hit.chunk.title,
                    section=hit.chunk.section,
                    score=hit.score,
                    cited=n in cited,
                )
                for n, hit in enumerate(hits, start=1)
            ],
            model=state.get("model"),
        )
