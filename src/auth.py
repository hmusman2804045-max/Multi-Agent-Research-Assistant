"""Authentication, Credential Verification, and Token Management Module (Phase 5).

Handles:
- Cryptographic password hashing (PBKDF2-HMAC-SHA256 with 100,000 rounds and random salt).
- Credential-gated user registration and authentication.
- Cryptographic JWT session token generation, verification, and user identity validation.
- Algorithm whitelisting (prevents 'none' algorithm bypass attacks).
- Mandatory expiration ('exp') and issued-at ('iat') claims.
- Strong typing with Pydantic.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Any, Dict, Optional, Tuple
import jwt
from pydantic import BaseModel, Field, field_validator

from src.config import settings
from src.logger import get_logger

logger = get_logger(__name__)

# Security constants for password derivation
PBKDF2_ROUNDS = 100_000
SALT_BYTES = 16
HASH_NAME = "sha256"
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


class AuthError(Exception):
    """Base exception for authentication and token validation failures."""
    pass


class TokenExpiredError(AuthError):
    """Raised when a JWT token has expired."""
    pass


class InvalidTokenError(AuthError):
    """Raised when a JWT token is malformed, invalid, or forged."""
    pass


class InvalidCredentialsError(AuthError):
    """Raised when provided user credentials (username/password) are incorrect."""
    pass


class UserAlreadyExistsError(AuthError):
    """Raised when registering a username that is already taken."""
    pass


class UserNotFoundError(AuthError):
    """Raised when the requested user account does not exist."""
    pass


class WeakPasswordError(AuthError):
    """Raised when a password fails policy requirements."""
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


def hash_password(password: str, salt_bytes: Optional[bytes] = None) -> Tuple[str, str]:
    """Derive a secure PBKDF2-HMAC-SHA256 hash for a given password.

    Args:
        password: Raw plain text password.
        salt_bytes: Optional raw salt bytes. If not provided, a random 16-byte salt is generated.

    Returns:
        Tuple of (salt_hex, hash_hex).
    """
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password cannot exceed {MAX_PASSWORD_LENGTH} characters.")

    salt = salt_bytes or secrets.token_bytes(SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        HASH_NAME,
        password.encode("utf-8"),
        salt,
        PBKDF2_ROUNDS
    )
    return salt.hex(), derived.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """Verify a plain password against a stored PBKDF2 hash using constant-time comparison.

    Args:
        password: The plain text password to verify.
        salt_hex: The hex-encoded salt string.
        hash_hex: The expected hex-encoded password hash.

    Returns:
        True if the password matches, False otherwise.
    """
    try:
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)
        actual_hash = hashlib.pbkdf2_hmac(
            HASH_NAME,
            password.encode("utf-8"),
            salt,
            PBKDF2_ROUNDS
        )
        return hmac.compare_digest(actual_hash, expected_hash)
    except Exception as e:
        logger.warning(f"Password verification encountered error: {e}")
        return False


def register_user(
    storage: Any,
    user_id: str,
    password: str,
    email: Optional[str] = None,
) -> Any:
    """Register a new user account with credentials.

    Args:
        storage: ResearchStorage instance.
        user_id: Requested unique user identifier.
        password: Plain text password meeting policy requirements.
        email: Optional email address.

    Returns:
        The created UserAccountDocument.

    Raises:
        UserAlreadyExistsError: If user_id is already registered.
        WeakPasswordError: If password is too short or invalid.
    """
    clean_user = user_id.strip()
    if not clean_user:
        raise ValueError("user_id cannot be empty")

    if storage.user_exists(clean_user):
        raise UserAlreadyExistsError(f"User '{clean_user}' already exists.")

    salt_hex, hash_hex = hash_password(password)

    from src.storage import UserAccountDocument
    user_doc = UserAccountDocument(
        user_id=clean_user,
        email=email.strip() if email else None,
        password_hash=hash_hex,
        salt=salt_hex,
        created_at=datetime.now(timezone.utc),
    )
    storage.save_user(user_doc)
    logger.info(f"User account '{clean_user}' successfully registered.")
    return user_doc


def authenticate_user(
    storage: Any,
    user_id: str,
    password: str,
) -> Tuple[Any, str]:
    """Verify credentials and issue a signed JWT access token.

    Args:
        storage: ResearchStorage instance.
        user_id: Username / user identifier.
        password: Plain text password to check.

    Returns:
        Tuple of (UserAccountDocument, jwt_token_string).

    Raises:
        UserNotFoundError: If user_id does not exist.
        InvalidCredentialsError: If password does not match.
    """
    clean_user = user_id.strip()
    user_doc = storage.get_user(clean_user)
    if not user_doc:
        raise UserNotFoundError(f"User '{clean_user}' not found.")

    if not verify_password(password, user_doc.salt, user_doc.password_hash):
        logger.warning(f"Failed authentication attempt for user '{clean_user}'.")
        raise InvalidCredentialsError("Invalid username or password.")

    token = create_access_token(user_id=clean_user, email=user_doc.email)
    logger.info(f"User '{clean_user}' authenticated successfully.")
    return user_doc, token


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
