"""Application logic: run the question flow under one deadline and shape the result."""

import asyncio
from typing import Any

from policydesk.errors import ModelTimeout
from policydesk.graph import RagState
from policydesk.logs import request_id_var
from policydesk.schemas import AskResponse, Source


class AskService:
    def __init__(self, graph: Any, request_timeout_seconds: float) -> None:
        self._graph = graph
        self._timeout = request_timeout_seconds

    async def ask(self, question: str) -> AskResponse:
        try:
            async with asyncio.timeout(self._timeout):
                state: RagState = await self._graph.ainvoke({"question": question})
        except TimeoutError:
            raise ModelTimeout(f"No answer within the {self._timeout:g} s request deadline.") from None

        hits = state.get("hits", [])
        cited = state.get("cited", set())
        return AskResponse(
            request_id=request_id_var.get(),
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
