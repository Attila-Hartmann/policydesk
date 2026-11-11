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
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def chunk_markdown(filename: str, text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    """One chunk per section; a section is named by its heading path (`Parent › Child`). The first `#` heading is
    the document title. Text before the first section becomes an "Overview" chunk. Headings inside fenced code
    blocks are text. Section bodies longer than max_chars are split at paragraph boundaries.
    IDs are `<file stem>:<NN>` in document order."""
    stem = Path(filename).stem
    title: str | None = None
    open_headings: list[tuple[int, str]] = []
    sections: list[tuple[str, list[str]]] = [("Overview", [])]
    in_fence = False
    for line in text.replace("\r\n", "\n").split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
        m = None if in_fence else _HEADING.match(line)
        if m is None:
            sections[-1][1].append(line)
            continue
        level, heading = len(m.group(1)), m.group(2)
        if level == 1 and title is None:
            title = heading
            continue
        open_headings = [(lvl, h) for lvl, h in open_headings if lvl < level] + [(level, heading)]
        sections.append((" › ".join(h for _, h in open_headings), []))
    title = title or stem

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
    chunks = [c for f in files for c in chunk_markdown(f.name, f.read_text(encoding="utf-8"))]
    if not chunks:
        raise StartupError(f"No Markdown documents with text found in {docs_dir}.")
    return chunks


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

    batches = list(batched([c.text for c in chunks], EMBED_BATCH))
    log_event(logger, "index_build_started", chunks=len(chunks), batches=len(batches), model=embedder.model)
    vectors: list[list[float]] = []
    for n, batch in enumerate(batches, start=1):
        vectors += await embedder.embed(batch)
        log_event(logger, "index_batch_embedded", batch=n, of=len(batches))
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
