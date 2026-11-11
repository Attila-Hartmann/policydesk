# ADR-002: Section-based Markdown chunking with deterministic IDs

Status: accepted

## Context

The corpus is ~10 short policy documents written in Markdown, each a set of headed sections (one rule or topic per section). Answers usually live in one section; some questions span two documents.

## Decision

- One chunk per `##`/`###` section. The chunk text starts with `<document title> › <section heading>`, so each chunk carries its context for both the embedding and the model.
- Sections longer than 1,200 characters are split at paragraph boundaries into pieces of at most 1,200 characters. No overlap: boundaries are semantic, so overlap would mostly duplicate text.
- Chunk IDs are `<file-stem>:<NN>` in document order. Files are read in sorted order with normalised line endings, so the same files always produce the same chunks and IDs.
- The index fingerprint is a SHA-256 of the chunk texts, the chunker parameters and the embedding model. Ingest skips work when the fingerprint is unchanged.

## Alternatives

- **Fixed-size windows with overlap** (e.g. 500 tokens / 50 overlap): format-agnostic, but splits rules mid-sentence and needs a tokenizer dependency. Better for long unstructured text, which this corpus isn't.
- **LangChain `MarkdownHeaderTextSplitter`**: same idea, extra dependency, less control over IDs. Our splitter is ~40 lines and unit-tested.
- **Whole documents as chunks**: documents are short, but whole-document vectors blur distinct rules and waste context tokens.

## Consequences

- Retrieval quality depends on documents having sensible headings. That holds for policies, and the README says so.
- Content-based IDs (hashes) would survive section reordering; positional IDs are more readable in responses. At this size, readability wins.
