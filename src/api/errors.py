"""Exception -> HTTP status mapping for the Phase 7 API.

Every core-module exception is translated here, once, so route handlers stay free of
error handling. Messages are always the exact text raised by the core module: the API
layer never invents its own error copy.
"""

from typing import Any, Dict, Tuple

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.auth import (
    AuthError,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenExpiredError,
    UserAlreadyExistsError,
    UserNotFoundError,
    WeakPasswordError,
)
from src.logger import get_logger
from src.rate_limiter import (
    AccountLockedError,
    BurstRateLimitExceededError,
    DailyLimitExceededError,
    RateLimitExceededError,
)

logger = get_logger(__name__)


def describe_exception(exc: Exception) -> Tuple[int, Dict[str, Any]]:
    """Map a core-module exception onto an (http_status, error_payload) pair.

    Shared by the JSON exception handlers and by the SSE stream, so a quota failure looks
    identical whether it surfaced on a normal response or inside an event stream.
    """
    message = str(exc)

    # --- Rate limiting & quotas -------------------------------------------------------
    if isinstance(exc, DailyLimitExceededError):
        # The two daily caps are distinct: 'personal' means this user spent their own
        # allocation, 'global' means the shared service-wide pool is empty for everyone.
        return status.HTTP_429_TOO_MANY_REQUESTS, {
            "error": "daily_limit_exceeded",
            "message": message,
            "retry_after_seconds": exc.retry_after_seconds,
            "cap_scope": getattr(exc, "scope", "personal"),
        }

    if isinstance(exc, BurstRateLimitExceededError):
        return status.HTTP_429_TOO_MANY_REQUESTS, {
            "error": "burst_rate_limit_exceeded",
            "message": message,
            "retry_after_seconds": exc.retry_after_seconds,
        }

    if isinstance(exc, RateLimitExceededError):
        return status.HTTP_429_TOO_MANY_REQUESTS, {
            "error": f"{exc.limit_type}_rate_limit_exceeded",
            "message": message,
            "retry_after_seconds": exc.retry_after_seconds,
        }

    # --- Authentication ---------------------------------------------------------------
    if isinstance(exc, AccountLockedError):
        return status.HTTP_423_LOCKED, {
            "error": "account_locked",
            "message": message,
            "remaining_lockout_seconds": exc.remaining_lockout_seconds,
        }

    if isinstance(exc, TokenExpiredError):
        return status.HTTP_401_UNAUTHORIZED, {"error": "token_expired", "message": message}

    if isinstance(exc, InvalidTokenError):
        return status.HTTP_401_UNAUTHORIZED, {"error": "invalid_token", "message": message}

    if isinstance(exc, InvalidCredentialsError):
        return status.HTTP_401_UNAUTHORIZED, {"error": "invalid_credentials", "message": message}

    if isinstance(exc, UserNotFoundError):
        return status.HTTP_401_UNAUTHORIZED, {"error": "user_not_found", "message": message}

    if isinstance(exc, UserAlreadyExistsError):
        return status.HTTP_409_CONFLICT, {"error": "user_already_exists", "message": message}

    if isinstance(exc, WeakPasswordError):
        return status.HTTP_400_BAD_REQUEST, {"error": "weak_password", "message": message}

    if isinstance(exc, AuthError):
        return status.HTTP_401_UNAUTHORIZED, {"error": "auth_error", "message": message}

    # --- Input validation (sanitize_user_input, storage key validation, config) --------
    if isinstance(exc, ValueError):
        return status.HTTP_400_BAD_REQUEST, {"error": "invalid_request", "message": message}

    return status.HTTP_500_INTERNAL_SERVER_ERROR, {
        "error": "internal_error",
        "message": "An unexpected error occurred while processing the request.",
    }


def _json_error(exc: Exception) -> JSONResponse:
    http_status, payload = describe_exception(exc)
    headers = {}
    retry_after = payload.get("retry_after_seconds") or payload.get("remaining_lockout_seconds")
    if retry_after:
        headers["Retry-After"] = str(int(retry_after))
    return JSONResponse(status_code=http_status, content=payload, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    """Install handlers translating core-module exceptions into HTTP responses."""

    handled = (AuthError, RateLimitExceededError, AccountLockedError, ValueError)

    for exc_type in handled:
        @app.exception_handler(exc_type)
        async def _handler(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
            return _json_error(exc)

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:  # noqa: ARG001
        """Normalize HTTPException onto the same error envelope every other error uses."""
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            payload = detail
        else:
            payload = {"error": "http_error", "message": str(detail)}
        return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:  # noqa: ARG001
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []) if p not in ("body", "query"))
        message = first.get("msg", "Invalid request.")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "validation_error",
                "message": f"{field}: {message}" if field else message,
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
        logger.exception(f"Unhandled error serving {request.method} {request.url.path}: {exc}")
        return _json_error(exc)
