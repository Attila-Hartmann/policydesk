"""HTTP layer: routes, the error contract, request-id middleware, and wiring (the lifespan is the composition root)."""

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from policydesk.config import Settings
from policydesk.errors import PolicydeskError
from policydesk.graph import ModelSlots, build_graph
from policydesk.logs import log_event, request_id_var
from policydesk.ports import ChatModel, Embedder
from policydesk.providers import OpenAICompatibleChat, OpenAICompatibleEmbedder, make_client
from policydesk.schemas import (
    Answer,
    AskRequest,
    AskResponse,
    ErrorBody,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    IndexStats,
)
from policydesk.service import AskService
from policydesk.store import VectorIndex

logger = logging.getLogger("policydesk.api")

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# The single place where domain error codes become HTTP statuses (ADR-005).
_STATUS = {"model_timeout": 504, "model_rate_limited": 503, "overloaded": 503, "model_error": 502}
DISCONNECT_POLL_SECONDS = 0.5
_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorResponse, "description": description}
    for status, description in {
        422: "Invalid request (`invalid_request`)",
        502: "Model provider failed or rejected the call (`model_error`)",
        503: "Rate-limited by the provider (`model_rate_limited`) or no free model slot (`overloaded`)",
        504: "No answer within the request deadline (`model_timeout`)",
    }.items()
}


def create_app(settings: Settings, *, chat: ChatModel | None = None, embedder: Embedder | None = None) -> FastAPI:
    """Real providers are built from settings; tests pass fakes instead."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = None
        chat_model, embed_model = chat, embedder
        if chat_model is None or embed_model is None:
            client = make_client(settings)
            chat_model = chat_model or OpenAICompatibleChat(client, settings.chat_model, settings.reasoning_effort)
            embed_model = embed_model or OpenAICompatibleEmbedder(client, settings.embedding_model)
        index = VectorIndex.load(settings.index_path, embed_model.model)
        slots = ModelSlots(settings.max_concurrent_model_calls, settings.queue_timeout_seconds)
        graph = build_graph(
            embed_model, chat_model, index, slots, top_k=settings.top_k, min_score=settings.min_relevance_score
        )
        app.state.service = AskService(graph, settings.request_timeout_seconds)
        app.state.health = HealthResponse(
            chat_model=chat_model.model,
            embedding_model=index.meta.embedding_model,
            index=IndexStats(documents=index.meta.documents, chunks=len(index.chunks), built_at=index.meta.built_at),
        )
        log_event(logger, "api_ready", chat_model=chat_model.model, embedding_model=embed_model.model)
        yield
        if client is not None:
            await client.close()

    app = FastAPI(
        title="policydesk",
        version="0.1.0",
        summary="Answers employee questions from internal policy documents, with sources.",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(PolicydeskError)
    async def domain_error(_: Request, exc: PolicydeskError) -> JSONResponse:
        log_event(
            logger, "request_failed", logging.WARNING, code=exc.code, reason=exc.message, cause=repr(exc.__cause__)
        )
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        return _error(_STATUS.get(exc.code, 500), exc.code, exc.message, exc.retryable, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Only location and message: pydantic's error also carries the input, which may be personal data.
        # For unparseable JSON the location is a character offset, not a field.
        details = [
            ErrorDetail(
                field="body" if err["type"] == "json_invalid" else ".".join(str(p) for p in err["loc"][1:]) or "body",
                reason=err["msg"],
            )
            for err in exc.errors()
        ]
        return _error(422, "invalid_request", "The request body is invalid.", False, details=details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, f"http_{exc.status_code}")
        return _error(exc.status_code, code, str(exc.detail), False, headers=dict(exc.headers) if exc.headers else None)

    @app.post("/ask", response_model=AskResponse, responses=_ERROR_RESPONSES, tags=["questions"])
    async def ask(body: AskRequest, request: Request) -> AskResponse | JSONResponse:
        """Answer a question from the policy documents and list the excerpts used.

        If no excerpt is relevant enough, `outcome` is `no_relevant_context` and the model is not called."""
        service: AskService = request.app.state.service
        answer = await cancel_on_disconnect(request, service.ask(body.question))
        if answer is None:  # the client is gone; nobody reads this response, it only shows up in the access log
            log_event(logger, "client_disconnected", logging.WARNING)
            return _error(499, "client_closed_request", "The client closed the connection.", False)
        return AskResponse(request_id=request_id_var.get(), **answer.model_dump())

    @app.get("/health", response_model=HealthResponse, tags=["operations"])
    async def health(request: Request) -> HealthResponse:
        """Liveness of this process: index loaded, models verified at startup. Does not call the model."""
        result: HealthResponse = request.app.state.health
        return result

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    return app


class RequestContextMiddleware:
    """Request id, access log and the last-resort 500, as plain ASGI middleware. Starlette's @app.middleware("http")
    (BaseHTTPMiddleware) would hide the client's disconnect from the endpoint, which cancel_on_disconnect needs."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = Headers(scope=scope).get("x-request-id", "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request_id_var.set(request_id)
        start = time.perf_counter()
        status = 500
        started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status, started
            if message["type"] == "http.response.start":
                started, status = True, message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:  # anything the handlers did not map: log the trace, return a generic 500
            logger.exception("unhandled_error")
            if not started:
                response = _error(
                    500, "internal_error", "Internal error. See the server log for this request id.", False
                )
                await response(scope, receive, send_with_request_id)
        finally:
            log_event(
                logger,
                "request",
                logging.DEBUG if scope["path"] == "/health" else logging.INFO,  # container probes every 10 s
                method=scope["method"],
                path=scope["path"],
                status=status,
                ms=round((time.perf_counter() - start) * 1000),
            )


class Disconnectable(Protocol):  # the part of starlette's Request used below; tests pass a stub
    async def is_disconnected(self) -> bool: ...


async def cancel_on_disconnect(request: Disconnectable, work: Coroutine[None, None, Answer]) -> Answer | None:
    """Run `work`, but cancel it if the client disconnects. Without this an abandoned request keeps its model slot
    until the deadline: on a single-slot local setup, everyone else gets 503 in the meantime. Returns None if
    the client went away."""
    task = asyncio.create_task(work)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=DISCONNECT_POLL_SECONDS)
            if done:
                return task.result()
            if await request.is_disconnected():
                return None
    finally:
        if not task.done():  # client gone, or this handler itself cancelled: stop the work and free the slot
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def _error(
    status: int,
    code: str,
    message: str,
    retryable: bool,
    *,
    details: list[ErrorDetail] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code, message=message, retryable=retryable, request_id=request_id_var.get(), details=details
        )
    )
    return JSONResponse(body.model_dump(exclude_none=True), status_code=status, headers=headers)
