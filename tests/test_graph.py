import asyncio
from pathlib import Path

import pytest

from policydesk.errors import Overloaded
from policydesk.graph import ModelSlots, build_graph
from policydesk.ingest import ingest
from policydesk.prompts import cited_numbers, user_prompt
from policydesk.store import Chunk, Hit
from tests.conftest import FakeChat, FakeEmbedder


def run_graph(docs_dir: Path, tmp_path: Path, question: str, chat: FakeChat) -> dict[str, object]:
    async def go() -> dict[str, object]:
        index, _ = await ingest(docs_dir, tmp_path / "index.json", FakeEmbedder())
        graph = build_graph(FakeEmbedder(), chat, index, ModelSlots(1, 1), top_k=3, min_score=0.3)
        state: dict[str, object] = await graph.ainvoke({"question": question})
        return state

    return asyncio.run(go())


def test_routes_to_generate_when_a_chunk_passes_the_threshold(docs_dir: Path, tmp_path: Path) -> None:
    chat = FakeChat()

    state = run_graph(docs_dir, tmp_path, "How many days of annual leave do employees receive?", chat)

    assert state["outcome"] == "answered"
    assert [hit.chunk.id for hit in state["hits"]] == ["leave:00"]  # type: ignore[attr-defined]
    assert state["cited"] == {1}
    assert len(chat.prompts) == 1


def test_routes_to_no_context_below_the_threshold(docs_dir: Path, tmp_path: Path) -> None:
    chat = FakeChat()

    state = run_graph(docs_dir, tmp_path, "Who won the football match yesterday?", chat)

    assert state["outcome"] == "no_relevant_context"
    assert state["hits"] == []
    assert chat.prompts == []


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("EUR 45 [1].", {1}),
        ("See [2][3] and [1, 3].", {1, 2, 3}),
        ("Out of range [0] [4] [12].", set()),
        ("No citations at all.", set()),
        ("Range [1-3] and en dash [1–2].", {1, 2, 3}),
        ("Semicolon [1; 3].", {1, 3}),
        ("Labelled [Excerpt 2] and [excerpts 1, 3].", {1, 2, 3}),
        ("Not a citation: [EUR 45], [see policy].", set()),
        ("Range past the end [2-99].", {2, 3}),
    ],
)
def test_cited_numbers(answer: str, expected: set[int]) -> None:
    assert cited_numbers(answer, count=3) == expected


def test_user_prompt_numbers_excerpts_in_rank_order_inside_delimiters() -> None:
    hits = [Hit(Chunk(f"d:{i}", "d.md", "T", "S", f"text {i}"), 0.9 - i / 10) for i in range(2)]

    prompt = user_prompt("Why?", hits)

    assert prompt == "<excerpts>\n[1] text 0\n\n[2] text 1\n</excerpts>\n\nQuestion: Why?"


def test_model_slots_fail_fast_when_all_busy() -> None:
    async def go() -> None:
        slots = ModelSlots(size=1, wait_seconds=0.05)
        async with slots.slot():
            with pytest.raises(Overloaded) as caught:
                async with slots.slot():
                    pass
        assert caught.value.retry_after == 10
        async with slots.slot():  # released again after use
            pass

    asyncio.run(go())
