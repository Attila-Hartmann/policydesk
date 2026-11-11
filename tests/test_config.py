from pathlib import Path

import pytest

from policydesk.config import Settings, load_settings
from policydesk.errors import StartupError

REPO = Path(__file__).resolve().parents[1]


def test_defaults_are_the_local_ollama_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here

    settings = load_settings()

    assert (settings.base_url, settings.chat_model, settings.embedding_model) == (
        "http://localhost:11434/v1",
        "qwen3:4b-instruct",
        "bge-m3",
    )
    assert settings.reasoning_effort is None


@pytest.mark.parametrize(
    ("sample", "base_url", "chat_model", "embedding_model", "reasoning_effort"),
    [
        (".env.example", "http://ollama:11434/v1", "qwen3:4b-instruct", "bge-m3", None),
        (".env.openai.example", "https://api.openai.com/v1", "gpt-6-luna", "text-embedding-3-small", "none"),
    ],
)
def test_env_samples_are_valid(
    sample: str, base_url: str, chat_model: str, embedding_model: str, reasoning_effort: str | None
) -> None:
    settings = Settings(_env_file=REPO / sample)  # type: ignore[call-arg]

    assert (settings.base_url, settings.chat_model, settings.embedding_model) == (base_url, chat_model, embedding_model)
    assert settings.reasoning_effort == reasoning_effort
    assert settings.api_key.get_secret_value() == ""  # samples never contain a key


def test_invalid_values_name_the_variable_but_never_echo_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "sk-very-secret")
    monkeypatch.setenv("MIN_RELEVANCE_SCORE", "1.5")
    monkeypatch.setenv("TOP_K", "zero")

    with pytest.raises(StartupError) as caught:
        load_settings(_env_file=None)

    message = str(caught.value)
    assert "MIN_RELEVANCE_SCORE" in message and "TOP_K" in message
    assert "sk-very-secret" not in message and "1.5" not in message and "zero" not in message


def test_api_key_is_masked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "sk-very-secret")

    assert "sk-very-secret" not in repr(load_settings(_env_file=None))
