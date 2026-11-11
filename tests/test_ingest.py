import asyncio
from pathlib import Path

import pytest

from policydesk.errors import StartupError
from policydesk.ingest import chunk_markdown, ingest, load_chunks
from tests.conftest import FakeEmbedder

REPO_DOCS = Path(__file__).resolve().parents[1] / "data" / "policies"

DOC = """# Expense Policy

Owner: Finance

## Receipts

Attach receipts above HUF 5,000.

## Deadlines

Submit within 30 days.

Late claims need approval.
"""


def test_one_chunk_per_section_with_title_prefix_and_stable_ids() -> None:
    chunks = chunk_markdown("expenses.md", DOC)

    assert [c.id for c in chunks] == ["expenses:00", "expenses:01", "expenses:02"]
    assert [c.section for c in chunks] == ["Overview", "Receipts", "Deadlines"]
    assert {c.title for c in chunks} == {"Expense Policy"}
    assert chunks[1].text == "Expense Policy › Receipts\n\nAttach receipts above HUF 5,000."
    assert chunks[2].text.endswith("Submit within 30 days.\n\nLate claims need approval.")


def test_long_section_is_split_at_paragraph_boundaries() -> None:
    body = "\n\n".join(f"Paragraph {i} " + "x" * 30 for i in range(5))
    chunks = chunk_markdown("long.md", f"# Long\n\n## Rules\n\n{body}\n", max_chars=90)

    assert [c.section for c in chunks] == ["Rules"] * 3
    assert all(c.text.count("Paragraph") in (1, 2) for c in chunks)
    assert "".join(c.text for c in chunks).count("Paragraph") == 5  # nothing lost, nothing duplicated


def test_single_oversized_paragraph_stays_whole() -> None:
    chunks = chunk_markdown("big.md", "# Big\n\n## One\n\n" + "y" * 500, max_chars=100)

    assert len(chunks) == 1
    assert chunks[0].text.endswith("y" * 500)


def test_line_endings_and_missing_title_are_handled() -> None:
    assert chunk_markdown("doc.md", DOC.replace("\n", "\r\n")) == chunk_markdown("doc.md", DOC)
    assert chunk_markdown("no-title.md", "## A\n\ntext")[0].title == "no-title"


def test_sample_corpus_chunks_deterministically_with_unique_ids() -> None:
    first, second = load_chunks(REPO_DOCS), load_chunks(REPO_DOCS)

    assert first == second
    assert len({c.id for c in first}) == len(first)
    assert len({c.document for c in first}) == 9
    assert all(c.title != Path(c.document).stem for c in first)  # every document has a real title
    assert max(len(c.text) for c in first) < 1500


def test_empty_docs_dir_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(StartupError, match="No Markdown documents"):
        load_chunks(tmp_path)


def test_ingest_skips_when_fingerprint_unchanged_and_rebuilds_when_it_changes(docs_dir: Path, tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    embedder = FakeEmbedder()

    _, built = asyncio.run(ingest(docs_dir, index_path, embedder))
    calls_after_build = embedder.calls
    _, rebuilt_same = asyncio.run(ingest(docs_dir, index_path, embedder))
    (docs_dir / "leave.md").write_text("# Leave Policy\n\n## Annual leave\n\n30 days.\n", encoding="utf-8")
    _, rebuilt_after_edit = asyncio.run(ingest(docs_dir, index_path, embedder))
    index, rebuilt_other_model = asyncio.run(ingest(docs_dir, index_path, FakeEmbedder(model="other-embed")))

    assert (built, rebuilt_same, rebuilt_after_edit, rebuilt_other_model) == (True, False, True, True)
    assert calls_after_build == 1
    assert index.meta.embedding_model == "other-embed"


def test_ingest_rebuilds_a_corrupt_index(docs_dir: Path, tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    index_path.write_text("{not json", encoding="utf-8")

    index, rebuilt = asyncio.run(ingest(docs_dir, index_path, FakeEmbedder()))

    assert rebuilt and len(index.chunks) == 4
