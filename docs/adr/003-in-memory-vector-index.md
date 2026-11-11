# ADR-003: Exact in-memory vector search over a JSON index file

Status: accepted

## Context

About 50 chunks of 1,024–1,536 dimensions. The index changes only when the documents change. It is rebuilt at container start when the fingerprint differs. One API instance in the reference setup.

## Decision

Ingest writes `var/index.json`: metadata (embedding model, dimensions, fingerprint, built_at), chunks and float32 vectors. The API loads it once at startup into a normalised NumPy matrix and answers each query with one matrix-vector product (exact cosine similarity), then sorts, applies the threshold and takes the top k.

The file is written atomically (temp file and rename), so a running reader never sees a half-written index.

## Alternatives

- **Chroma / FAISS / LanceDB**: approximate or embedded vector stores. At 50 vectors exact search is already sub-millisecond, so they add dependency weight and opaque on-disk formats for no gain.
- **pgvector or Azure AI Search**: the right choice when there are several writers, many instances, a corpus that doesn't fit in memory, metadata filtering or hybrid search. They add a service to run and a migration story. This is the documented next step, not the starting point.

## Consequences

- Several instances each hold their own read-only copy: fine while the index is small and rebuilt by a deploy or an ingest job, wrong once documents change at runtime.
- Memory is chunks × dimensions × 4 bytes (float32): 50 × 1,536 is about 0.3 MB. At 100k chunks it would be ~600 MB per instance, and the JSON file would be several GB of text, slow to load long before search time matters. That is the point to switch (to a binary format at first, then to a real store).
- JSON is inspectable with any editor, which helps debugging and review.
