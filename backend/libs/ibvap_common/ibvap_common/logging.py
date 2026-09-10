"""Structured JSON logging with a correlation ID propagated end-to-end
(SAS §10: "correlation ID propagated from Gateway through every downstream
call and into pipeline messages").
"""

from __future__ import annotations

import contextlib
import contextvars
import uuid
from collections.abc import Awaitable, Callable, Iterator

import structlog
from fastapi import FastAPI, Request, Response

_correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)

CORRELATION_ID_HEADER = "X-Correlation-ID"
CORRELATION_ID_FIELD = "correlationId"  # key used in Redis Streams/Pub-Sub payloads


def get_correlation_id() -> str:
    return _correlation_id_var.get()


def new_correlation_id() -> str:
    """Mints a fresh id for work with no inbound request/message to inherit
    one from -- e.g. a camera worker originating a new frame."""
    return str(uuid.uuid4())


@contextlib.contextmanager
def correlation_id_context(correlation_id: str) -> Iterator[None]:
    """Binds a correlation id for the duration of processing one background
    unit of work (a consumed Stream/Pub-Sub message) so logs emitted while
    handling it -- and any outbound calls made via `correlated_headers()`
    during that time -- carry it, the same way the HTTP middleware below
    does for a request. Falls back to minting a fresh id if handed an empty
    one, so a message from an older producer that predates this field still
    gets *a* traceable id rather than silently logging with none."""
    token = _correlation_id_var.set(correlation_id or new_correlation_id())
    try:
        yield
    finally:
        _correlation_id_var.reset(token)


def correlated_headers() -> dict[str, str]:
    """Headers to attach to an outbound HTTP call so the correlation id
    bound in the current context (via the request middleware or
    `correlation_id_context`) continues into the service being called.
    Returns `{}` when nothing is bound, so merging this in is always safe."""
    cid = get_correlation_id()
    return {CORRELATION_ID_HEADER: cid} if cid else {}


def configure_logging(service_name: str) -> None:
    """Call once at service startup."""

    def add_service_name(logger, method_name, event_dict):
        event_dict["service"] = service_name
        return event_dict

    def add_correlation_id(logger, method_name, event_dict):
        cid = get_correlation_id()
        if cid:
            event_dict["correlationId"] = cid
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_service_name,
            add_correlation_id,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def install_correlation_id_middleware(app: FastAPI) -> None:
    """Reads/generates X-Correlation-ID on every request and echoes it back."""

    @app.middleware("http")
    async def correlation_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(CORRELATION_ID_HEADER)
        correlation_id = incoming or str(uuid.uuid4())
        token = _correlation_id_var.set(correlation_id)
        try:
            response = await call_next(request)
        finally:
            _correlation_id_var.reset(token)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
