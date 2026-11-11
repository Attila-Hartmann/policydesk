from pathlib import Path

import pytest

from policydesk.errors import ModelError, StartupError
from policydesk.store import Chunk, IndexMeta, VectorIndex


def make_index(vectors: list[list[float]], model: str = "m") -> VectorIndex:
    chunks = [Chunk(f"doc:{i:02d}", "doc.md", "Doc", f"S{i}", f"text {i}") for i in range(len(vectors))]
    meta = IndexMeta(embedding_model=model, dimensions=2, fingerprint="f", built_at="2026-01-01T00:00:00", documents=1)
    return VectorIndex(chunks, vectors, meta)


def test_search_orders_by_score_filters_by_threshold_and_limits() -> None:
    index = make_index([[1, 0], [0.8, 0.6], [0, 1], [0.6, 0.8]])

    hits = index.search([1, 0], top_k=2, min_score=0.5)

    assert [(h.chunk.id, h.score) for h in hits] == [("doc:00", 1.0), ("doc:01", 0.8)]
    assert [h.chunk.id for h in index.search([1, 0], top_k=10, min_score=0.5)] == ["doc:00", "doc:01", "doc:03"]
    assert index.search([-1, 0], top_k=3, min_score=0.1) == []


def test_ties_are_broken_by_chunk_id() -> None:
    index = make_index([[0, 1], [1, 0], [1, 0]])

    assert [h.chunk.id for h in index.search([1, 0], top_k=2, min_score=0.5)] == ["doc:01", "doc:02"]


def test_scores_are_cosine_regardless_of_vector_length() -> None:
    index = make_index([[10, 0], [0, 0]])  # a zero vector must not divide by zero

    hits = index.search([0.5, 0], top_k=2, min_score=-1)

    assert [h.score for h in hits] == [1.0, 0.0]


def test_query_with_wrong_dimensions_is_a_model_error() -> None:
    with pytest.raises(ModelError, match="3 dimensions"):
        make_index([[1, 0]]).search([1, 0, 0], top_k=1, min_score=0)


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "index.json"
    original = make_index([[1, 0], [0.6, 0.8]])

    original.save(path)
    loaded = VectorIndex.load(path, "m")

    assert loaded.meta == original.meta
    assert loaded.chunks == original.chunks
    assert loaded.search([0.6, 0.8], 2, 0) == original.search([0.6, 0.8], 2, 0)
    assert not path.with_suffix(".tmp").exists()


def test_refuses_index_from_another_embedding_model(tmp_path: Path) -> None:
    path = tmp_path / "index.json"
    make_index([[1, 0]], model="bge-m3").save(path)

    with pytest.raises(StartupError, match=r"built with embedding model 'bge-m3'.*'text-embedding-3-small'"):
        VectorIndex.load(path, "text-embedding-3-small")


def test_missing_index_explains_what_to_run(tmp_path: Path) -> None:
    with pytest.raises(StartupError, match="policydesk ingest"):
        VectorIndex.load(tmp_path / "missing.json")


def test_vector_count_must_match_chunks() -> None:
    meta = IndexMeta("m", 2, "f", "t", 1)
    with pytest.raises(ValueError, match="expected 1 vectors"):
        VectorIndex([Chunk("a:00", "a.md", "A", "S", "t")], [[1, 0], [0, 1]], meta)
