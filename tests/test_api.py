import asyncio
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient

from policydesk.api import cancel_on_disconnect
from policydesk.errors import ModelError, ModelRateLimited, ModelTimeout, Overloaded
from policydesk.graph import ModelSlots
from policydesk.prompts import NO_CONTEXT_ANSWER
from policydesk.schemas import Answer
from tests.conftest import FakeChat, FakeEmbedder

IN_DOMAIN = "What is the daily meal allowance in Vienna?"
OFF_TOPIC = "Who won the football match yesterday?"


def assert_error(response: Any, status: int, code: str, retryable: bool) -> dict[str, Any]:
    assert response.status_code == status
    error: dict[str, Any] = response.json()["error"]
    assert error["code"] == code
    assert error["retryable"] is retryable
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert error["message"]
    return error


def test_ask_returns_answer_with_sources(client: TestClient, chat: FakeChat) -> None:
    response = client.post("/ask", json={"question": IN_DOMAIN})

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "answered"
    assert body["answer"] == f"Answer to: {IN_DOMAIN} [1]"
    assert body["model"] == "fake-chat"
    assert body["request_id"] == response.headers["X-Request-ID"]
    top = body["sources"][0]
    assert top["chunk_id"] == "travel:01"
    assert (top["document"], top["title"], top["section"]) == ("travel.md", "Travel Policy", "Meal allowance")
    assert top["cited"] is True
    assert all(s["cited"] is False for s in body["sources"][1:])
    assert [s["score"] for s in body["sources"]] == sorted((s["score"] for s in body["sources"]), reverse=True)
    assert len(chat.prompts) == 1
    assert "EUR 45" in chat.prompts[0]  # the retrieved excerpt reached the model


def test_question_is_stripped_before_use(client: TestClient, chat: FakeChat) -> None:
    response = client.post("/ask", json={"question": f"   {IN_DOMAIN}\n"})

    assert response.status_code == 200
    assert chat.prompts[0].endswith(f"Question: {IN_DOMAIN}")


@pytest.mark.parametrize(
    "payload",
    [
        {"question": ""},
        {"question": "   \n\t "},
        {"question": "ab"},
        {"question": "x" * 501},
        {},
        {"question": 42},
        {"question": None},
        {"question": IN_DOMAIN, "top_k": 50},
        [IN_DOMAIN],
    ],
    ids=["empty", "whitespace", "too_short", "too_long", "missing", "wrong_type", "null", "extra_field", "not_object"],
)
def test_invalid_input(client: TestClient, chat: FakeChat, payload: Any) -> None:
    response = client.post("/ask", json=payload)

    error = assert_error(response, 422, "invalid_request", retryable=False)
    assert error["details"] and all(d["field"] and d["reason"] for d in error["details"])
    assert chat.prompts == []


def test_malformed_json(client: TestClient) -> None:
    response = client.post("/ask", content=b'{"question": ', headers={"Content-Type": "application/json"})

    error = assert_error(response, 422, "invalid_request", retryable=False)
    assert error["details"] == [{"field": "body", "reason": "JSON decode error"}]


def test_validation_error_does_not_echo_input(client: TestClient) -> None:
    secret = "x" * 495 + "TOKEN"
    response = client.post("/ask", json={"question": secret + "!" * 10})

    assert "TOKEN" not in response.text


def test_no_relevant_context_does_not_call_model(client: TestClient, chat: FakeChat) -> None:
    response = client.post("/ask", json={"question": OFF_TOPIC})

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "no_relevant_context"
    assert body["answer"] == NO_CONTEXT_ANSWER
    assert body["sources"] == []
    assert body["model"] is None
    assert chat.prompts == []


def test_model_timeout_returns_504(make_client: Callable[..., TestClient], chat: FakeChat) -> None:
    client = make_client(request_timeout_seconds=0.2, queue_timeout_seconds=0.1)
    chat.delay = lambda question: 2.0

    response = client.post("/ask", json={"question": IN_DOMAIN})

    error = assert_error(response, 504, "model_timeout", retryable=True)
    assert "0.2 s" in error["message"]


@pytest.mark.parametrize(
    ("exc", "status", "code", "retryable", "retry_after"),
    [
        (ModelTimeout("slow"), 504, "model_timeout", True, None),
        (ModelRateLimited("429", retry_after=7), 503, "model_rate_limited", True, "7"),
        (Overloaded("busy", retry_after=10), 503, "overloaded", True, "10"),
        (ModelError("HTTP 500", retryable=True), 502, "model_error", True, None),
        (ModelError("HTTP 401", retryable=False), 502, "model_error", False, None),
    ],
    ids=["timeout", "rate_limited", "overloaded", "provider_down", "provider_rejected"],
)
def test_model_errors(
    client: TestClient, chat: FakeChat, exc: Exception, status: int, code: str, retryable: bool, retry_after: str | None
) -> None:
    chat.error = exc

    response = client.post("/ask", json={"question": IN_DOMAIN})

    assert_error(response, status, code, retryable)
    assert response.headers.get("Retry-After") == retry_after


def test_embedding_error_uses_same_contract(client: TestClient, embedder: FakeEmbedder, chat: FakeChat) -> None:
    embedder.error = ModelError("Could not reach the embedding model.", retryable=True)

    response = client.post("/ask", json={"question": IN_DOMAIN})

    assert_error(response, 502, "model_error", retryable=True)
    assert chat.prompts == []


def test_overloaded_when_no_slot(make_client: Callable[..., TestClient], chat: FakeChat) -> None:
    client = make_client(max_concurrent_model_calls=1, queue_timeout_seconds=0.1)
    chat.delay = lambda question: 1.0 if question.endswith("slow?") else 0.0

    with ThreadPoolExecutor(2) as pool:
        slow = pool.submit(client.post, "/ask", json={"question": "Vienna meal allowance, slow?"})
        deadline = time.monotonic() + 5
        while not chat.prompts:  # wait until the slow request holds the only slot
            assert time.monotonic() < deadline, "slow request never reached the model"
            time.sleep(0.01)
        fast = client.post("/ask", json={"question": IN_DOMAIN})

    assert slow.result().status_code == 200
    assert_error(fast, 503, "overloaded", retryable=True)
    assert fast.headers["Retry-After"] == "10"


def test_timeout_releases_the_model_slot(make_client: Callable[..., TestClient], chat: FakeChat) -> None:
    client = make_client(max_concurrent_model_calls=1, request_timeout_seconds=0.3, queue_timeout_seconds=0.1)
    chat.delay = lambda question: 2.0 if question.endswith("slow?") else 0.0

    timed_out = client.post("/ask", json={"question": "Vienna meal allowance, slow?"})
    after = client.post("/ask", json={"question": IN_DOMAIN})

    assert_error(timed_out, 504, "model_timeout", retryable=True)
    assert after.status_code == 200


def test_unexpected_error_is_500_without_details(client: TestClient, chat: FakeChat, json_logs: Any) -> None:
    chat.error = RuntimeError("database password is hunter2")

    response = client.post("/ask", json={"question": IN_DOMAIN})

    assert_error(response, 500, "internal_error", retryable=False)
    assert "hunter2" not in response.text
    assert any(line["event"] == "unhandled_error" and "RuntimeError" in line["exc"] for line in json_logs())


@pytest.mark.parametrize(
    ("method", "path", "status", "code"),
    [("GET", "/nope", 404, "not_found"), ("GET", "/ask", 405, "method_not_allowed")],
)
def test_unknown_route_and_method_use_error_schema(
    client: TestClient, method: str, path: str, status: int, code: str
) -> None:
    assert_error(client.request(method, path), status, code, retryable=False)


def test_health_reports_models_and_index_without_model_calls(
    client: TestClient, chat: FakeChat, embedder: FakeEmbedder
) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert (body["chat_model"], body["embedding_model"]) == ("fake-chat", "fake-embed")
    assert body["index"]["documents"] == 2
    assert body["index"]["chunks"] == 4
    assert body["index"]["built_at"]
    assert chat.prompts == [] and embedder.calls == 0


def test_root_redirects_to_docs(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


def test_request_id_propagates_to_header_body_and_logs(client: TestClient, json_logs: Any) -> None:
    response = client.post("/ask", json={"question": IN_DOMAIN}, headers={"X-Request-ID": "req-123"})

    assert response.headers["X-Request-ID"] == "req-123"
    assert response.json()["request_id"] == "req-123"
    events = {line["event"]: line for line in json_logs() if line["request_id"] == "req-123"}
    assert {"retrieval", "generation", "request"} <= events.keys()
    assert events["request"]["status"] == 200
    assert events["generation"]["prompt_tokens"] == 100


def test_unsafe_request_id_is_replaced(client: TestClient) -> None:
    response = client.post("/ask", json={"question": IN_DOMAIN}, headers={"X-Request-ID": "x" * 65})

    assert response.headers["X-Request-ID"] != "x" * 65
    assert len(response.headers["X-Request-ID"]) == 32


def test_logs_do_not_contain_question_or_answer(client: TestClient, json_logs: Any) -> None:
    client.post("/ask", json={"question": "Kovács Béla asks: what is the meal allowance in Vienna?"})

    logged = str(json_logs())
    assert "Kovács" not in logged
    assert "Vienna" not in logged


def test_concurrent_requests_do_not_mix(make_client: Callable[..., TestClient], chat: FakeChat) -> None:
    client = make_client(max_concurrent_model_calls=20, queue_timeout_seconds=4)
    # Later questions finish first, so responses interleave inside the event loop.
    chat.delay = lambda question: 0.2 - int(question.split("#")[1]) * 0.01
    questions = [f"What is the meal allowance in Vienna, case #{i}" for i in range(20)]

    with ThreadPoolExecutor(20) as pool:
        responses = list(pool.map(lambda q: client.post("/ask", json={"question": q}), questions))

    for question, response in zip(questions, responses, strict=True):
        assert response.status_code == 200
        assert response.json()["answer"] == f"Answer to: {question} [1]"
        assert response.json()["request_id"] == response.headers["X-Request-ID"]  # contextvar not shared
    assert len({r.headers["X-Request-ID"] for r in responses}) == 20


class StubRequest:
    def __init__(self, disconnect_after: float) -> None:
        self._at = time.monotonic() + disconnect_after

    async def is_disconnected(self) -> bool:
        return time.monotonic() >= self._at


def test_client_disconnect_cancels_the_work_and_frees_the_slot() -> None:
    slots = ModelSlots(size=1, wait_seconds=0.1)
    finished: list[str] = []

    async def slow_answer() -> Answer:
        async with slots.slot():
            await asyncio.sleep(5)
            finished.append("slow")
        return Answer(outcome="answered", answer="late", sources=[], model="m")

    async def scenario() -> None:
        result = await cancel_on_disconnect(StubRequest(disconnect_after=0.2), slow_answer())
        assert result is None
        async with slots.slot():  # free again immediately, not after 5 s
            pass

    started = time.monotonic()
    asyncio.run(scenario())

    assert time.monotonic() - started < 2
    assert finished == []


def test_completed_work_is_returned_when_the_client_stays() -> None:
    async def quick() -> Answer:
        return Answer(outcome="no_relevant_context", answer="none", sources=[], model=None)

    result = asyncio.run(cancel_on_disconnect(StubRequest(disconnect_after=60), quick()))

    assert result is not None and result.answer == "none"
