import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import openai
import pytest
from pydantic import SecretStr

from policydesk.config import Settings
from policydesk.errors import ModelError, ModelRateLimited, ModelTimeout, PolicydeskError
from policydesk.providers import OpenAICompatibleChat, OpenAICompatibleEmbedder, make_client

Handler = Callable[[httpx.Request], httpx.Response]


def client_with(handler: Handler) -> openai.AsyncOpenAI:
    return openai.AsyncOpenAI(
        base_url="http://model.test/v1",
        api_key="k",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def chat_reply(content: str | None) -> dict[str, Any]:
    return {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
    }


def test_make_client_takes_everything_from_settings() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, base_url="http://x:1/v1", api_key=SecretStr(""), request_timeout_seconds=7, llm_max_retries=2
    )

    client = make_client(settings)

    assert str(client.base_url) == "http://x:1/v1/"
    assert client.api_key == "unused"
    assert (client.timeout, client.max_retries) == (7, 2)


@pytest.mark.parametrize(("effort", "expected"), [(None, None), ("none", "none")])
def test_chat_request_and_reasoning_effort_only_when_set(effort: str | None, expected: str | None) -> None:
    sent: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(200, json=chat_reply("  EUR 45 [1]  "))

    completion = asyncio.run(OpenAICompatibleChat(client_with(handler), "m", effort).complete("sys", "usr"))

    assert completion.text == "EUR 45 [1]"
    assert (completion.prompt_tokens, completion.completion_tokens) == (120, 30)
    assert sent["model"] == "m" and sent["temperature"] == 0
    assert sent["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]
    assert sent.get("reasoning_effort") == expected


def test_embeddings_are_requested_as_floats_and_returned_in_input_order() -> None:
    sent: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        data = [{"object": "embedding", "index": i, "embedding": [float(i)]} for i in (1, 0)]
        return httpx.Response(200, json={"object": "list", "model": "e", "data": data, "usage": {}})

    vectors = asyncio.run(OpenAICompatibleEmbedder(client_with(handler), "e").embed(["a", "b"]))

    assert sent == {"model": "e", "input": ["a", "b"], "encoding_format": "float"}
    assert vectors == [[0.0], [1.0]]


def fails_with(status: int, headers: dict[str, str] | None = None) -> Handler:
    return lambda request: httpx.Response(status, headers=headers, json={"error": {"message": "nope"}})


def raises(exc: Exception) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


@pytest.mark.parametrize(
    ("handler", "error_type", "retryable", "retry_after"),
    [
        (raises(httpx.ReadTimeout("slow")), ModelTimeout, True, None),
        (raises(httpx.ConnectError("refused")), ModelError, True, None),
        (fails_with(429, {"retry-after": "3"}), ModelRateLimited, True, 3),
        (fails_with(429), ModelRateLimited, True, 10),
        (fails_with(500), ModelError, True, None),
        (fails_with(503), ModelError, True, None),
        (fails_with(401), ModelError, False, None),
        (fails_with(404), ModelError, False, None),
        (fails_with(400), ModelError, False, None),
        (lambda request: httpx.Response(200, content=b"<html>not an API</html>"), ModelError, False, None),
    ],
    ids=["timeout", "connect", "429_header", "429_default", "500", "503", "401", "404", "400", "garbage"],
)
def test_sdk_errors_become_domain_errors(
    handler: Handler, error_type: type[PolicydeskError], retryable: bool, retry_after: int | None
) -> None:
    with pytest.raises(error_type) as caught:
        asyncio.run(OpenAICompatibleChat(client_with(handler), "m").complete("s", "u"))

    assert type(caught.value) is error_type
    assert caught.value.retryable is retryable
    assert caught.value.retry_after == retry_after


def test_empty_answer_is_a_retryable_model_error() -> None:
    handler: Handler = lambda request: httpx.Response(200, json=chat_reply(None))  # noqa: E731

    with pytest.raises(ModelError, match="empty answer"):
        asyncio.run(OpenAICompatibleChat(client_with(handler), "m").complete("s", "u"))


def test_embedding_errors_are_translated_too() -> None:
    with pytest.raises(ModelError) as caught:
        asyncio.run(OpenAICompatibleEmbedder(client_with(fails_with(404)), "e").embed(["a"]))

    assert caught.value.retryable is False
    assert "embedding model" in caught.value.message


def test_missing_embeddings_are_detected() -> None:
    handler: Handler = lambda request: httpx.Response(  # noqa: E731
        200, json={"object": "list", "model": "e", "data": [], "usage": {}}
    )

    with pytest.raises(ModelError, match="Expected 1 embeddings"):
        asyncio.run(OpenAICompatibleEmbedder(client_with(handler), "e").embed(["a"]))


def test_non_api_embedding_response_is_reported_as_configuration_error() -> None:
    handler: Handler = lambda request: httpx.Response(200, content=b"<html></html>")  # noqa: E731

    with pytest.raises(ModelError, match="OpenAI-compatible"):
        asyncio.run(OpenAICompatibleEmbedder(client_with(handler), "e").embed(["a"]))
