"""RFC 7807 problem+json error shape, per API Specification §10.

    {
      "type": "https://ibvap.dev/errors/not-found",
      "title": "Camera not found",
      "status": 404,
      "detail": "No camera with id BOP-99-CAM-01",
      "traceId": "a1b2c3"
    }
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ibvap_common.logging import get_correlation_id


class ApiError(Exception):
    """Base exception every service should raise for expected error conditions."""

    def __init__(
        self,
        *,
        status_code: int,
        title: str,
        detail: str | None = None,
        error_type: str = "about:blank",
    ) -> None:
        self.status_code = status_code
        self.title = title
        self.detail = detail
        self.error_type = error_type
        super().__init__(detail or title)


class NotFoundError(ApiError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Resource not found",
            detail=detail,
            error_type="https://ibvap.dev/errors/not-found",
        )


class ConflictError(ApiError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            title="Conflict",
            detail=detail,
            error_type="https://ibvap.dev/errors/conflict",
        )


class UnauthorizedError(ApiError):
    def __init__(self, detail: str = "Authentication required") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            title="Unauthorized",
            detail=detail,
            error_type="https://ibvap.dev/errors/unauthorized",
        )


class ForbiddenError(ApiError):
    def __init__(self, detail: str = "Insufficient role for this action") -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            title="Forbidden",
            detail=detail,
            error_type="https://ibvap.dev/errors/forbidden",
        )


def _problem(status_code: int, title: str, detail: str | None, error_type: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "type": error_type,
            "title": title,
            "status": status_code,
            "detail": detail,
            "traceId": get_correlation_id(),
        },
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _problem(exc.status_code, exc.title, exc.detail, exc.error_type)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _problem(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Validation error",
            str(exc.errors()),
            "https://ibvap.dev/errors/validation",
        )

    @app.exception_handler(Exception)
    async def handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
        return _problem(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal server error",
            "An unexpected error occurred",
            "https://ibvap.dev/errors/internal",
        )
