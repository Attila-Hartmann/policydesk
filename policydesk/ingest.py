"""Document preparation: Markdown → section chunks → embeddings → index file (ADR-002)."""

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path

from policydesk.errors import StartupError
from policydesk.logs import log_event
from policydesk.ports import Embedder
from policydesk.store import Chunk, IndexMeta, VectorIndex

logger = logging.getLogger(__name__)

MAX_CHUNK_CHARS = 1200
EMBED_BATCH = 16  # keeps each embedding call short on a CPU-only Ollama
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def chunk_markdown(filename: str, text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    """One chunk per section (any heading below the `#` title); long sections split at paragraph boundaries.
    Text before the first section becomes an "Overview" chunk. IDs are `<file stem>:<NN>` in document order."""
    stem = Path(filename).stem
    title = stem
    sections: list[tuple[str, list[str]]] = [("Overview", [])]
    for line in text.replace("\r\n", "\n").split("\n"):
        m = _HEADING.match(line)
        if m and len(m.group(1)) == 1:
            title = m.group(2)
        elif m:
            sections.append((m.group(2), []))
        else:
            sections[-1][1].append(line)

    chunks: list[Chunk] = []
    for section, lines in sections:
        for piece in _pack_paragraphs("\n".join(lines), max_chars):
            chunks.append(
                Chunk(f"{stem}:{len(chunks):02d}", filename, title, section, f"{title} › {section}\n\n{piece}")
            )
    return chunks


def _pack_paragraphs(body: str, max_chars: int) -> list[str]:
    """Greedily pack whole paragraphs into pieces of at most max_chars. A single longer paragraph stays whole:
    splitting mid-sentence would hurt more than one oversized chunk."""
    pieces: list[str] = []
    for para in (p.strip() for p in re.split(r"\n\s*\n", body)):
        if not para:
            continue
        if pieces and len(pieces[-1]) + 2 + len(para) <= max_chars:
            pieces[-1] += "\n\n" + para
        else:
            pieces.append(para)
    return pieces


def load_chunks(docs_dir: Path) -> list[Chunk]:
    files = sorted(docs_dir.glob("*.md"))
    if not files:
        raise StartupError(f"No Markdown documents found in {docs_dir}.")
    return [c for f in files for c in chunk_markdown(f.name, f.read_text(encoding="utf-8"))]


def fingerprint(chunks: list[Chunk], embedding_model: str) -> str:
    payload = {"model": embedding_model, "max_chars": MAX_CHUNK_CHARS, "chunks": [[c.id, c.text] for c in chunks]}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


async def ingest(docs_dir: Path, index_path: Path, embedder: Embedder) -> tuple[VectorIndex, bool]:
    """Build the index unless an identical one exists. Returns (index, rebuilt)."""
    chunks = load_chunks(docs_dir)
    fp = fingerprint(chunks, embedder.model)
    existing = _load_if_current(index_path, fp)
    if existing is not None:
        log_event(logger, "index_up_to_date", chunks=len(chunks), path=str(index_path))
        return existing, False

    vectors: list[list[float]] = []
    for batch in batched([c.text for c in chunks], EMBED_BATCH):
        vectors += await embedder.embed(batch)
    meta = IndexMeta(
        embedding_model=embedder.model,
        dimensions=len(vectors[0]),
        fingerprint=fp,
        built_at=datetime.now(UTC).isoformat(timespec="seconds"),
        documents=len({c.document for c in chunks}),
    )
    index = VectorIndex(chunks, vectors, meta)
    index.save(index_path)
    log_event(logger, "index_built", chunks=len(chunks), documents=meta.documents, dimensions=meta.dimensions)
    return index, True


def _load_if_current(index_path: Path, fp: str) -> VectorIndex | None:
    if not index_path.exists():
        return None
    try:
        existing = VectorIndex.load(index_path)
    except (ValueError, KeyError, TypeError):
        return None  # unreadable or from an older format: rebuild
    return existing if existing.meta.fingerprint == fp else None
