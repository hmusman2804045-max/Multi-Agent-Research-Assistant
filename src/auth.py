"""Authentication and Token Management Module (Phase 5).

Handles JWT session token generation, verification, and user identity validation.
Adheres to strict security standards:
- Explicit algorithm restriction (prevents 'none' algorithm bypass attacks).
- Mandatory expiration ('exp') and issued-at ('iat') claims.
- Strong typing with Pydantic.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt
from pydantic import BaseModel, Field, field_validator

from src.config import settings
from src.logger import get_logger

logger = get_logger(__name__)


class AuthError(Exception):
    """Base exception for authentication and token validation failures."""
    pass


class TokenExpiredError(AuthError):
    """Raised when a JWT token has expired."""
    pass


class InvalidTokenError(AuthError):
    """Raised when a JWT token is malformed, invalid, or forged."""
    pass


class UserIdentity(BaseModel):
    """Represents an authenticated user identity extracted from a validated token."""
    user_id: str = Field(..., min_length=1, max_length=128, description="Unique identifier for the user.")
    email: Optional[str] = Field(default=None, description="Optional user email.")
    session_id: Optional[str] = Field(default=None, description="Optional linked research session identifier.")
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = Field(default=None)

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        v_clean = v.strip()
        if not v_clean:
            raise ValueError("user_id cannot be empty or only whitespace")
        # Prevent dangerous characters or directory traversal strings
        if any(c in v_clean for c in ["\0", "$", "\n", "\r"]):
            raise ValueError("user_id contains prohibited characters")
        return v_clean


def create_access_token(
    user_id: str,
    session_id: Optional[str] = None,
    email: Optional[str] = None,
    custom_claims: Optional[Dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None,
    secret_key: Optional[str] = None,
    algorithm: Optional[str] = None,
) -> str:
    """Create a signed JWT token for a given user and optional session.

    Args:
        user_id: The unique identifier for the user.
        session_id: Optional research session identifier linked to this token.
        email: Optional user email address.
        custom_claims: Optional dictionary of additional claims.
        expires_delta: Optional custom token expiration duration.
        secret_key: Secret key used to sign the token (defaults to settings.jwt_secret_key).
        algorithm: Hashing algorithm (defaults to settings.jwt_algorithm).

    Returns:
        Encoded and signed JWT string.
    """
    user_id_clean = user_id.strip()
    if not user_id_clean:
        raise ValueError("user_id cannot be empty")

    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.auth_token_expire_minutes)

    payload: Dict[str, Any] = {
        "sub": user_id_clean,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    if session_id:
        payload["session_id"] = session_id.strip()
    if email:
        payload["email"] = email.strip()
    if custom_claims:
        for k, v in custom_claims.items():
            if k not in payload:
                payload[k] = v

    key = secret_key or settings.jwt_secret_key
    algo = algorithm or settings.jwt_algorithm

    try:
        token = jwt.encode(payload, key, algorithm=algo)
        logger.debug(f"Generated JWT access token for user: {user_id_clean}")
        return token
    except Exception as e:
        logger.error(f"Failed to encode JWT token for user '{user_id_clean}': {e}")
        raise AuthError(f"Token generation failed: {e}") from e


def verify_access_token(
    token: str,
    secret_key: Optional[str] = None,
    algorithm: Optional[str] = None,
) -> UserIdentity:
    """Verify, decode, and validate a JWT access token.

    Args:
        token: The raw JWT string.
        secret_key: Secret key for verifying signature (defaults to settings.jwt_secret_key).
        algorithm: Expected signing algorithm (defaults to settings.jwt_algorithm).

    Returns:
        UserIdentity model representing the validated token claims.

    Raises:
        TokenExpiredError: If the token has expired.
        InvalidTokenError: If the token signature is invalid, forged, or missing required claims.
    """
    if not token or not isinstance(token, str):
        raise InvalidTokenError("Token must be a non-empty string")

    key = secret_key or settings.jwt_secret_key
    algo = algorithm or settings.jwt_algorithm

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[algo],
            options={
                "require": ["sub", "exp", "iat"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
            },
        )
    except jwt.ExpiredSignatureError as e:
        logger.warning("Token verification failed: Token has expired")
        raise TokenExpiredError("Token has expired") from e
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token verification failed: {e}")
        raise InvalidTokenError(f"Invalid token: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected error during token verification: {e}")
        raise InvalidTokenError(f"Token decoding failed: {e}") from e

    user_id = payload.get("sub")
    if not user_id:
        raise InvalidTokenError("Token payload missing required 'sub' (user_id) claim")

    iat_dt = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
    exp_dt = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    return UserIdentity(
        user_id=user_id,
        email=payload.get("email"),
        session_id=payload.get("session_id"),
        issued_at=iat_dt,
        expires_at=exp_dt,
    )
