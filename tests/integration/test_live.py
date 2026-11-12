"""End-to-end checks against a running policydesk API with real models: local (Ollama) or cloud, whichever mode
the stack was started in. Deselected by default; run with:

    docker compose up -d --build        # wait until `docker compose ps` shows the api as healthy
    uv run pytest -m integration

Model answers are not deterministic, so the checks look for the facts and sources, not exact wording."""

import os
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

API_URL = os.environ.get("API_URL", "http://localhost:8000")

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def api() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=API_URL, timeout=180) as client:
        try:
            client.get("/health").raise_for_status()
        except httpx.HTTPError:
            # Fail, not skip: running `-m integration` without a stack must not look like a pass.
            pytest.fail(f"No healthy policydesk API at {API_URL}; start it with `docker compose up` first")
        yield client


def ask(api: httpx.Client, question: str) -> dict[str, Any]:
    response = api.post("/ask", json={"question": question})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_health_reports_the_sample_index(api: httpx.Client) -> None:
    body = api.get("/health").json()

    assert body["status"] == "ok"
    assert body["index"]["documents"] == 9


def test_english_question_is_answered_from_the_right_section(api: httpx.Client) -> None:
    body = ask(api, "How much is the daily meal allowance in Vienna?")

    assert body["outcome"] == "answered"
    assert "45" in body["answer"]
    assert body["sources"][0]["chunk_id"] == "travel-and-expenses:05"
    assert body["sources"][0]["cited"] is True
    assert "Vienna: EUR 45" in body["sources"][0]["text"]


def test_hungarian_question_finds_the_english_policy(api: httpx.Client) -> None:
    body = ask(api, "Hány nap szabadság jár egy évben?")

    assert body["outcome"] == "answered"
    assert "25" in body["answer"]
    assert "leave.md" in {s["document"] for s in body["sources"]}


def test_cross_document_question_uses_both_policies(api: httpx.Client) -> None:
    body = ask(
        api,
        "I want to work remotely from Vienna for two weeks. Is that allowed, and do I get the Vienna meal allowance?",
    )

    assert body["outcome"] == "answered"
    assert {"remote-work.md", "travel-and-expenses.md"} <= {s["document"] for s in body["sources"]}


def test_off_topic_question_gets_no_context_without_a_model_call(api: httpx.Client) -> None:
    body = ask(api, "Who won the football World Cup in 2022?")

    assert body["outcome"] == "no_relevant_context"
    assert body["sources"] == [] and body["model"] is None


def test_empty_question_is_rejected_in_the_error_format(api: httpx.Client) -> None:
    response = api.post("/ask", json={"question": "  "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
