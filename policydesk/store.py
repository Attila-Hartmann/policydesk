"""Vector index: exact cosine search over a NumPy matrix, persisted as one JSON file (ADR-003)."""

import json
import os
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from policydesk.errors import ModelError, StartupError


@dataclass(frozen=True)
class Chunk:
    id: str
    document: str
    title: str
    section: str
    text: str


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


@dataclass(frozen=True)
class IndexMeta:
    embedding_model: str
    dimensions: int
    fingerprint: str
    built_at: str
    documents: int


class VectorIndex:
    def __init__(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]], meta: IndexMeta) -> None:
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.shape != (len(chunks), meta.dimensions):
            raise ValueError(f"expected {len(chunks)} vectors of {meta.dimensions} dims, got shape {matrix.shape}")
        self.chunks = list(chunks)
        self.meta = meta
        self._matrix = _normalise(matrix)

    def search(self, query: Sequence[float], top_k: int, min_score: float) -> list[Hit]:
        """Hits with score >= min_score, best first, at most top_k. Ties are broken by chunk id for stable output."""
        q = np.asarray(query, dtype=np.float32)
        if q.shape != (self.meta.dimensions,):
            raise ModelError(
                f"Query embedding has {q.size} dimensions, the index has {self.meta.dimensions}.", retryable=False
            )
        scores = self._matrix @ _normalise(q)
        ranked = sorted(range(len(self.chunks)), key=lambda i: (-scores[i], self.chunks[i].id))
        return [Hit(self.chunks[i], round(float(scores[i]), 4)) for i in ranked if scores[i] >= min_score][:top_k]

    def save(self, path: Path) -> None:
        """Atomic write: a reader never sees a half-written file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "meta": asdict(self.meta),
            "chunks": [asdict(c) for c in self.chunks],
            "vectors": self._raw_vectors(),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Path, embedding_model: str | None = None) -> "VectorIndex":
        """Load the index; refuse one built with a different embedding model than the configured one."""
        if not path.exists():
            raise StartupError(f"Index file {path} not found: run `python -m policydesk ingest` first.")
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        meta = IndexMeta(**data["meta"])
        if embedding_model is not None and meta.embedding_model != embedding_model:
            raise StartupError(
                f"Index {path} was built with embedding model '{meta.embedding_model}', but the configuration says "
                f"'{embedding_model}'. Vectors from different models are not comparable: run "
                "`python -m policydesk ingest` again."
            )
        return cls([Chunk(**c) for c in data["chunks"]], data["vectors"], meta)

    def _raw_vectors(self) -> list[list[float]]:
        # Rows are already normalised; storing them normalised is harmless for cosine search.
        return [[round(float(x), 6) for x in row] for row in self._matrix]


def _normalise(a: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
    norms = np.linalg.norm(a, axis=-1, keepdims=True)
    return (a / np.where(norms == 0, 1, norms)).astype(np.float32, copy=False)
