# ADR-005: Failure policy: one error format, one deadline, bounded retries, a concurrency cap

Status: accepted

## Context

The slow and unreliable part of every request is the model call: seconds of latency, provider rate limits, transient 5xx. On a CPU-only local setup there is also a hard throughput limit of about one generation at a time. Clients need to know whether to retry, and a request must not hang longer than a typical proxy timeout.

## Decision

- **One error body** for every non-2xx response: `{"error": {"code", "message", "retryable", "request_id"}}`. Validation errors add `details`. Status codes: 422 invalid input (including unparseable JSON, FastAPI's convention), 504 deadline exceeded, 503 rate-limited or overloaded (with `Retry-After`), 502 provider error (`retryable` says whether it was transient or a rejected call), 500 unexpected. The full table is in the README.
- **Translation at the edges**: `providers.py` turns SDK exceptions into domain errors; the API's exception handlers turn domain errors into HTTP. The graph does not catch them.
- **One deadline per request**: `REQUEST_TIMEOUT_SECONDS` (cloud 30 s, local 120 s) wraps the whole graph run (embedding, queue wait, generation) with `asyncio.timeout`. The worst-case latency is the deadline, not a sum of per-call timeouts and retries.
- **Retries**: the SDK's built-in exponential backoff with jitter, which honours `Retry-After`, only on connection errors, 408, 409, 429 and 5xx, and only while the deadline has time left. `LLM_MAX_RETRIES` is 2 for cloud and 0 for local, where a timed-out generation won't get faster on retry and the retry doubles the load.
- **Concurrency cap**: an `asyncio.Semaphore` per process limits in-flight chat calls (`MAX_CONCURRENT_MODEL_CALLS`: local 1, matching `OLLAMA_NUM_PARALLEL=1`; cloud 8). A request that waits longer than `QUEUE_TIMEOUT_SECONDS` (5 s) for a slot fails fast with `503 overloaded` and `Retry-After: 10`, instead of queueing until every request times out.

## Alternatives

- **Errors as `200` with an `error` field**: breaks HTTP semantics, proxies and client retry logic.
- **Own retry loop (tenacity)**: duplicates what the SDK already does correctly.
- **Per-call timeouts only**: the worst case becomes (retries + 1) × timeout + backoff + queue wait, which is easy to get wrong and goes past proxy limits.
- **Circuit breaker / fallback model**: useful once there is a second provider and real traffic; next step.

## Consequences

- Clients get a bounded response time and a machine-readable retry hint.
- The semaphore is per process, and the API runs one worker. With N instances the provider sees up to N × cap concurrent calls; a global limit needs a shared limiter (Redis) or an API-gateway quota. This is the documented next step.
