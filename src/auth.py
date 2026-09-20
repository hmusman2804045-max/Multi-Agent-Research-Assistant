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
from src.email_service import send_password_reset_email
from src.storage import PasswordResetToken
from src.rate_limiter import RateLimiter

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

    clean_email = email.strip().lower() if email else None
    if clean_email:
        existing_email_user = storage.find_user_by_email(clean_email)
        if existing_email_user:
            raise UserAlreadyExistsError(f"An account with email '{clean_email}' already exists.")

    salt_hex, hash_hex = hash_password(password)

    from src.storage import UserAccountDocument
    user_doc = UserAccountDocument(
        user_id=clean_user,
        email=clean_email,
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
        AccountLockedError: If account is locked due to repeated failed logins.
        UserNotFoundError: If user_id does not exist.
        InvalidCredentialsError: If password does not match.
    """
    from src.rate_limiter import RateLimiter, AccountLockedError

    clean_user = user_id.strip()
    limiter = RateLimiter(storage=storage)

    # 1. Check if account is temporarily locked out
    lockout_secs = limiter.check_login_lockout(clean_user)
    if lockout_secs:
        mins = max(1, (lockout_secs + 59) // 60)
        logger.warning(f"Blocked login attempt for locked account '{clean_user}'. {lockout_secs}s remaining.")
        raise AccountLockedError(
            f"Account '{clean_user}' is temporarily locked due to multiple failed login attempts. "
            f"Please wait {mins} minute(s) ({lockout_secs}s) before trying again.",
            remaining_lockout_seconds=lockout_secs,
        )

    user_doc = storage.get_user(clean_user)
    if not user_doc:
        limiter.record_login_attempt(clean_user, success=False)
        raise UserNotFoundError(f"User '{clean_user}' not found.")

    if not verify_password(password, user_doc.salt, user_doc.password_hash):
        limiter.record_login_attempt(clean_user, success=False)
        logger.warning(f"Failed authentication attempt for user '{clean_user}'.")
        raise InvalidCredentialsError("Invalid username or password.")

    # Successful login: reset failed login attempts
    limiter.record_login_attempt(clean_user, success=True)
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


def request_password_reset(
    storage: Any,
    user_id_or_email: str,
    rate_limiter: Optional[Any] = None,
) -> str:
    """Request a password reset link for a user account by username or email.

    Enforces rate limits to prevent email spamming and guarantees anti-enumeration
    by always returning an identical generic message.

    Args:
        storage: ResearchStorage instance.
        user_id_or_email: Target user_id or registered email.
        rate_limiter: Optional RateLimiter instance.

    Returns:
        Generic confirmation message (anti-enumeration defense).

    Raises:
        ValueError: If user_id_or_email is empty.
        RateLimitExceededError: If the rate limit for this identifier is exceeded.
    """
    if not user_id_or_email or not user_id_or_email.strip():
        raise ValueError("Username or email address cannot be empty.")

    clean_id = user_id_or_email.strip()

    # 1. Look up user account first (supports username or email)
    user = storage.find_user_by_email_or_id(clean_id)

    # 2. Enforce unified rate limit (keyed to resolved user_id if account exists)
    limiter = rate_limiter or RateLimiter(storage=storage)
    rate_identifier = f"user_{user.user_id}" if user else f"query_{clean_id.lower()}"
    limiter.check_password_reset_rate_limit(rate_identifier)

    # 3. If account exists and has email, create token and dispatch email
    if user and user.email:
        raw_token = secrets.token_urlsafe(32)
        now_dt = datetime.now(timezone.utc)
        expires_at = now_dt + timedelta(minutes=settings.password_reset_token_expire_minutes)

        token_doc = PasswordResetToken(
            token=raw_token,
            user_id=user.user_id,
            created_at=now_dt,
            expires_at=expires_at,
            used=False,
        )
        storage.save_reset_token(token_doc)

        reset_link = f"python main.py --reset-password {raw_token}"
        send_password_reset_email(to_email=user.email, reset_link=reset_link)
        logger.info(f"Initiated password reset for user '{user.user_id}'.")
    else:
        # Mitigate timing side-channels with simulated dummy cryptographic operations
        _ = secrets.token_urlsafe(32)
        _ = hashlib.pbkdf2_hmac(HASH_NAME, b"dummy_constant_timing_padding", b"dummy_salt_bytes", 10_000)
        logger.info(
            f"Password reset requested for non-existent or email-less identifier. Skipped delivery."
        )

    # 4. Anti-enumeration guaranteed uniform message
    return "If an account with that identifier exists, a password reset email has been sent."


def confirm_password_reset(
    storage: Any,
    token: str,
    new_password: str,
    rate_limiter: Optional[Any] = None,
) -> bool:
    """Confirm a password reset using a valid single-use reset token.

    Validates token expiration, hashes the new password with PBKDF2-HMAC-SHA256,
    marks the token used, and clears any active login lockout.

    Args:
        storage: ResearchStorage instance.
        token: Single-use reset token.
        new_password: New plain-text password.
        rate_limiter: Optional RateLimiter instance.

    Returns:
        True if password reset succeeded.

    Raises:
        InvalidTokenError: If token is invalid, missing, or already used.
        TokenExpiredError: If token expiration timestamp has elapsed.
        WeakPasswordError: If new password does not meet minimum policy requirements.
        UserNotFoundError: If associated user account cannot be found.
    """
    if not token or not token.strip():
        raise InvalidTokenError("Reset token must be a non-empty string.")

    clean_token = token.strip()
    token_doc = storage.get_reset_token(clean_token)

    if not token_doc:
        raise InvalidTokenError("Invalid or non-existent password reset token.")

    if token_doc.used:
        raise InvalidTokenError("This password reset token has already been used.")

    now_dt = datetime.now(timezone.utc)
    token_exp = token_doc.expires_at
    if token_exp.tzinfo is None:
        token_exp = token_exp.replace(tzinfo=timezone.utc)

    if now_dt >= token_exp:
        raise TokenExpiredError("Password reset token has expired (15-minute window elapsed).")

    # Fetch user account
    user = storage.get_user(token_doc.user_id)
    if not user:
        raise UserNotFoundError(f"User account '{token_doc.user_id}' associated with token was not found.")

    # Validate and hash new password using existing PBKDF2 logic
    salt_hex, hash_hex = hash_password(new_password)

    # Update user account
    user.salt = salt_hex
    user.password_hash = hash_hex
    storage.save_user(user)

    # Invalidate token
    storage.mark_reset_token_used(clean_token)

    # Reset any brute-force login lockout state for this user
    limiter = rate_limiter or RateLimiter(storage=storage)
    limiter.clear_login_lockout(user.user_id)

    logger.info(f"Password reset completed successfully for user '{user.user_id}'.")
    return True
