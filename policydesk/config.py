"""Configuration: every setting comes from the environment or `.env`. Switching between cloud and local
mode means changing these values, never code."""

from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from policydesk.errors import StartupError


class Settings(BaseSettings):
    # extra="ignore": .env also holds compose-only keys such as COMPOSE_PROFILES.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    # Model endpoint: any OpenAI-compatible API (OpenAI, Azure OpenAI v1, Ollama). Defaults = local Ollama on the host.
    base_url: str = "http://localhost:11434/v1"
    api_key: SecretStr = SecretStr("")
    chat_model: str = "qwen3:4b-instruct"
    embedding_model: str = "bge-m3"
    reasoning_effort: str | None = None  # sent only when set (e.g. "none" for OpenAI reasoning models)

    # Retrieval. The threshold belongs to the embedding model: recalibrate it when that changes (ADR-004).
    min_relevance_score: float = Field(0.5, gt=0, lt=1)
    top_k: int = Field(4, ge=1, le=10)

    # Failure policy (ADR-005).
    request_timeout_seconds: float = Field(120, gt=0)
    llm_max_retries: int = Field(0, ge=0, le=5)
    max_concurrent_model_calls: int = Field(1, ge=1)
    queue_timeout_seconds: float = Field(5, gt=0)

    docs_dir: Path = Path("data/policies")
    index_path: Path = Path("var/index.json")
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: Any) -> Any:
        return value or None


def load_settings(**overrides: Any) -> Settings:
    """Settings, or a StartupError that names the bad variables without echoing their values (one may be a key)."""
    try:
        return Settings(**overrides)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(map(str, err['loc'])).upper()}: {err['msg']}" for err in e.errors())
        raise StartupError(f"Invalid configuration: {problems}") from None
