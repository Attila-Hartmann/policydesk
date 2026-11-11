import json
from pathlib import Path
from typing import Any

import pytest

from policydesk import cli
from policydesk.errors import ModelError
from policydesk.ports import Completion
from tests.conftest import LEAVE, TRAVEL, FakeEmbedder


class FakeChatModel:
    error: Exception | None = None

    def __init__(self, client: Any, model: str, reasoning_effort: str | None = None) -> None:
        self.model = model

    async def complete(self, system: str, user: str) -> Completion:
        if self.error:
            raise self.error
        return Completion("OK")


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory with documents and a .env, and fake providers wired into the CLI."""
    docs = tmp_path / "data" / "policies"
    docs.mkdir(parents=True)
    (docs / "travel.md").write_text(TRAVEL, encoding="utf-8")
    (docs / "leave.md").write_text(LEAVE, encoding="utf-8")
    (tmp_path / ".env").write_text("EMBEDDING_MODEL=fake-embed\nMIN_RELEVANCE_SCORE=0.3\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "OpenAICompatibleEmbedder", lambda client, model: FakeEmbedder(model))
    monkeypatch.setattr(cli, "OpenAICompatibleChat", FakeChatModel)
    monkeypatch.setattr(FakeChatModel, "error", None)
    return tmp_path


def test_ingest_builds_the_index(workdir: Path) -> None:
    assert cli.main(["ingest"]) == 0

    index = json.loads((workdir / "var" / "index.json").read_text(encoding="utf-8"))
    assert index["meta"]["embedding_model"] == "fake-embed"
    assert len(index["chunks"]) == 4


def test_serve_checks_models_then_starts_uvicorn(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: dict[str, Any] = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: started.update(kwargs))

    assert cli.main(["serve"]) == 0

    assert started["host"] == "127.0.0.1" and started["port"] == 8000
    assert (workdir / "var" / "index.json").exists()


def test_serve_fails_fast_when_model_check_fails(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(FakeChatModel, "error", ModelError("The language model returned HTTP 404.", retryable=False))
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: pytest.fail("must not start"))

    assert cli.main(["serve"]) == 1

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["event"] == "startup_failed"
    assert "HTTP 404" in line["reason"] and "BASE_URL" in line["reason"]


def test_invalid_configuration_exits_with_1(workdir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOP_K", "99")

    assert cli.main(["ingest"]) == 1


def test_search_prints_scores_against_the_threshold(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["ingest"])
    capsys.readouterr()

    assert cli.main(["search", "daily meal allowance Vienna"]) == 0

    out = capsys.readouterr().out.splitlines()
    assert out[0] == "threshold MIN_RELEVANCE_SCORE=0.3"
    assert "PASS" in out[1] and "travel:01" in out[1]


def test_search_without_index_fails(workdir: Path) -> None:
    assert cli.main(["search", "anything"]) == 1
