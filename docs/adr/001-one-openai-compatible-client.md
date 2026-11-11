# ADR-001: One OpenAI-compatible client for cloud and local models

Status: accepted

## Context

The brief requires a paid cloud mode and a free local mode, switched by configuration only, with provider-specific details kept in one place. The candidates for the cloud are OpenAI and Azure OpenAI; for local, Ollama.

All three serve the same OpenAI-compatible HTTP API for chat completions and embeddings: OpenAI natively, Azure OpenAI through its v1 endpoint (`https://<resource>.openai.azure.com/openai/v1/`, GA since August 2025), Ollama under `/v1`.

## Decision

Use the official `openai` Python SDK (async client) for every mode. The mode is a set of environment variables: `BASE_URL`, `API_KEY`, `CHAT_MODEL`, `EMBEDDING_MODEL`, plus optional request parameters (`REASONING_EFFORT`). `providers.py` is the only module that imports `openai`; it builds the clients and translates SDK exceptions into domain errors.

The application depends on two small protocols, `ChatModel` and `Embedder`. Their second implementations are the fakes the tests use.

## Alternatives

- **LangChain chat model classes** (`ChatOpenAI`, `ChatOllama`, `AzureChatOpenAI`): one class per provider means provider choice in code, more dependencies, and the same HTTP calls underneath. Rejected.
- **One adapter class per provider behind an interface**: three implementations of the same protocol, differing only in base URL. Rejected as an abstraction without a real difference.
- **Ollama native API** (`/api/chat`): gives access to `think` and `keep_alive`, but makes the local mode a separate code path. Not needed with a non-thinking model.

## Consequences

- Switching mode never touches code; the same image runs every mode.
- A provider without an OpenAI-compatible API (for example Bedrock's Converse API) would need a second `ChatModel` implementation. The protocol is the seam for that; it is not built now.
- Provider quirks are config, not code: `REASONING_EFFORT=none` is sent only when set, because Ollama doesn't need it.
