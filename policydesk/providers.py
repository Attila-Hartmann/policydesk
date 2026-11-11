"""The only module that knows about the model provider. OpenAI, Azure OpenAI (v1 endpoint) and Ollama all speak the
OpenAI-compatible API, so one client covers them; the mode is just configuration (ADR-001). SDK exceptions are
translated here into domain errors, so nothing above this layer depends on the SDK."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import openai
from openai.types import CreateEmbeddingResponse
from openai.types.chat import ChatCompletion

from policydesk.config import Settings
from policydesk.errors import ModelError, ModelRateLimited, ModelTimeout
from policydesk.ports import Completion

DEFAULT_RETRY_AFTER = 10
_NOT_OPENAI_COMPATIBLE = "Unexpected response from the {what}: is BASE_URL an OpenAI-compatible /v1 endpoint?"


def make_client(settings: Settings) -> openai.AsyncOpenAI:
    """The SDK retries connection errors, timeouts, 408, 409, 429 and 5xx with exponential backoff and jitter.
    Each attempt gets an equal share of the request deadline, so a hung attempt is retried instead of eating the
    whole budget; the deadline in AskService still cancels whatever is in flight when it expires."""
    return openai.AsyncOpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key.get_secret_value() or "unused",  # Ollama ignores the key; the SDK requires one
        timeout=settings.request_timeout_seconds / (settings.llm_max_retries + 1),
        max_retries=settings.llm_max_retries,
    )


@contextmanager
def _translate_errors(what: str) -> Iterator[None]:
    # Order matters: APITimeoutError is an APIConnectionError, RateLimitError is an APIStatusError.
    try:
        yield
    except openai.APITimeoutError as e:
        raise ModelTimeout(f"The {what} did not answer in time.") from e
    except openai.RateLimitError as e:
        if e.code == "insufficient_quota":  # billing, not load: retrying does not help
            raise ModelError(f"The {what} account has no quota left.", retryable=False) from e
        raise ModelRateLimited(f"The {what} is rate-limiting requests.", retry_after=_retry_after(e)) from e
    except openai.APIConnectionError as e:
        raise ModelError(f"Could not reach the {what}.", retryable=True) from e
    except openai.APIStatusError as e:
        transient = e.status_code >= 500 or e.status_code in (408, 409)
        raise ModelError(f"The {what} returned HTTP {e.status_code}.", retryable=transient) from e
    except openai.OpenAIError as e:  # e.g. a response the SDK could not validate: deterministic, not transient
        raise ModelError(f"Unexpected response from the {what}.", retryable=False) from e


def _retry_after(e: openai.APIStatusError) -> int:
    value = e.response.headers.get("retry-after", "")
    return max(1, int(float(value))) if value.replace(".", "", 1).isdigit() else DEFAULT_RETRY_AFTER


class OpenAICompatibleChat:
    def __init__(self, client: openai.AsyncOpenAI, model: str, reasoning_effort: str | None = None) -> None:
        self._client = client
        self.model = model
        self._extra: dict[str, Any] = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}

    async def complete(self, system: str, user: str) -> Completion:
        with _translate_errors("language model"):
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0,
                **self._extra,
            )
        if not isinstance(response, ChatCompletion) or not response.choices:
            raise ModelError(_NOT_OPENAI_COMPATIBLE.format(what="language model"), retryable=False)
        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise ModelError("The language model returned an empty answer.", retryable=False)
        usage = response.usage
        return Completion(text, usage.prompt_tokens if usage else None, usage.completion_tokens if usage else None)


class OpenAICompatibleEmbedder:
    def __init__(self, client: openai.AsyncOpenAI, model: str) -> None:
        self._client = client
        self.model = model

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        with _translate_errors("embedding model"):
            # The SDK asks for base64 by default; "float" is the format every compatible server supports.
            response = await self._client.embeddings.create(
                model=self.model, input=list(texts), encoding_format="float"
            )
        if not isinstance(response, CreateEmbeddingResponse):
            raise ModelError(_NOT_OPENAI_COMPATIBLE.format(what="embedding model"), retryable=False)
        if len(response.data) != len(texts):
            raise ModelError(f"Expected {len(texts)} embeddings, got {len(response.data)}.", retryable=True)
        return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
