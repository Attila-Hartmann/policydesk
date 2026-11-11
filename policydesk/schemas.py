"""HTTP request/response models. They also drive the OpenAPI docs at /docs."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class AskRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"question": "How much is the daily meal allowance in Vienna?"},
                {"question": "Hány nap szabadság jár egy évben?"},
            ]
        },
    )

    question: Question = Field(description="The employee's question, in English or Hungarian (3–500 characters).")


class Source(BaseModel):
    chunk_id: str = Field(examples=["travel-and-expenses:05"])
    document: str = Field(examples=["travel-and-expenses.md"])
    title: str = Field(examples=["Travel and Expenses Policy"])
    section: str = Field(examples=["Daily meal allowance"])
    score: float = Field(description="Cosine similarity between question and excerpt.", examples=[0.71])
    cited: bool = Field(description="True if the answer cites this excerpt as [n].")


class Answer(BaseModel):
    outcome: Literal["answered", "no_relevant_context"] = Field(
        description="`no_relevant_context`: no excerpt passed the relevance threshold, the model was not called."
    )
    answer: str
    sources: list[Source] = Field(description="Excerpts given to the model, best match first.")
    model: str | None = Field(description="Chat model that wrote the answer; null if no model was called.")


class AskResponse(Answer):
    request_id: str = Field(description="Same as the X-Request-ID response header; quote it when reporting a problem.")


class ErrorDetail(BaseModel):
    field: str
    reason: str


class ErrorBody(BaseModel):
    code: str = Field(examples=["model_timeout"])
    message: str
    retryable: bool
    request_id: str
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class IndexStats(BaseModel):
    documents: int
    chunks: int
    built_at: str


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    chat_model: str
    embedding_model: str
    index: IndexStats
