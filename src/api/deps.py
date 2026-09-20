"""Shared dependencies for the Phase 7 HTTP API.

Holds the single process-wide storage handle, the lazily constructed research pipeline,
and the FastAPI dependencies that turn an incoming request into either an authenticated
identity or a scoped guest identity.
"""

import re
import threading
from typing import Optional

from fastapi import Depends, Header, HTTPException, Query, status

from src.auth import UserIdentity, verify_access_token
from src.logger import get_logger
from src.pipeline import ResearchPipeline
from src.rate_limiter import RateLimiter
from src.storage import ResearchStorage

logger = get_logger(__name__)

# Guest identifiers are client-supplied, so the transport layer bounds them to a safe
# shape before they are ever used as a storage/rate-limit key.
_GUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_storage: Optional[ResearchStorage] = None
_rate_limiter: Optional[RateLimiter] = None
_pipeline: Optional[ResearchPipeline] = None
_pipeline_lock = threading.Lock()


def get_storage() -> ResearchStorage:
    """Return the process-wide ResearchStorage handle."""
    global _storage
    if _storage is None:
        _storage = ResearchStorage()
    return _storage


def get_rate_limiter() -> RateLimiter:
    """Return the process-wide RateLimiter bound to the shared storage handle."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(storage=get_storage())
    return _rate_limiter


def get_pipeline() -> ResearchPipeline:
    """Return the process-wide ResearchPipeline, constructing it on first use.

    Construction validates API keys and builds LLM clients, so it is deferred until a
    research request actually arrives - auth and history endpoints stay usable without it.
    """
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                _pipeline = ResearchPipeline(storage=get_storage())
    return _pipeline


def reset_state(
    storage: Optional[ResearchStorage] = None,
    rate_limiter: Optional[RateLimiter] = None,
    pipeline: Optional[ResearchPipeline] = None,
) -> None:
    """Replace the process-wide handles. Used by tests to inject isolated fixtures."""
    global _storage, _rate_limiter, _pipeline
    _storage = storage
    _rate_limiter = rate_limiter if rate_limiter is not None else (
        RateLimiter(storage=storage) if storage is not None else None
    )
    _pipeline = pipeline


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    """Pull the raw JWT out of an 'Authorization: Bearer <token>' header."""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def get_optional_identity(
    authorization: Optional[str] = Header(default=None),
) -> Optional[UserIdentity]:
    """Resolve an authenticated identity if a valid bearer token was supplied.

    A malformed or expired token is an explicit error rather than a silent downgrade to
    guest: a user whose session expired must be told, not quietly de-authenticated.
    """
    token = _extract_bearer_token(authorization)
    if not token:
        return None
    return verify_access_token(token)


def require_identity(
    identity: Optional[UserIdentity] = Depends(get_optional_identity),
) -> UserIdentity:
    """Require an authenticated identity, rejecting anonymous requests with 401."""
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return identity


def get_guest_id(
    session_id: Optional[str] = Query(
        default=None,
        description="Client-generated guest session identifier used to scope guest rate limits.",
    ),
) -> Optional[str]:
    """Validate and return the client-supplied guest session identifier."""
    if session_id is None:
        return None
    candidate = session_id.strip()
    if not candidate:
        return None
    if not _GUEST_ID_RE.match(candidate):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id must be 1-64 characters of letters, digits, '-' or '_'.",
        )
    return candidate
