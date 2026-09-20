"""Authentication routes.

Each route maps one-to-one onto an existing, already-hardened function in `src.auth` and
mirrors the corresponding CLI flow in main.py. Password hashing, JWT signing, lockout
tracking, anti-enumeration and its timing floor all live in `src.auth` / `src.rate_limiter`
and are never reimplemented here.
"""

from fastapi import APIRouter, Depends, status

from src.api.deps import get_rate_limiter, get_storage
from src.api.schemas import (
    AuthResponse,
    ForgotPasswordRequest,
    GenericMessageResponse,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from src.auth import (
    authenticate_user,
    confirm_password_reset,
    register_user,
    request_password_reset,
    verify_access_token,
)
from src.storage import ResearchStorage

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_response(user_doc, token: str) -> AuthResponse:
    identity = verify_access_token(token)
    return AuthResponse(
        user_id=user_doc.user_id,
        email=user_doc.email,
        access_token=token,
        expires_at=identity.expires_at.isoformat() if identity.expires_at else None,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    storage: ResearchStorage = Depends(get_storage),
) -> AuthResponse:
    """Register a new account and issue a session token.

    Mirrors the CLI `--register` flow, which also authenticates immediately afterwards so
    the caller receives a usable token in one round trip.
    """
    register_user(
        storage,
        user_id=payload.username,
        password=payload.password,
        email=payload.email,
    )
    user_doc, token = authenticate_user(
        storage,
        user_id=payload.username,
        password=payload.password,
    )
    return _auth_response(user_doc, token)


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    storage: ResearchStorage = Depends(get_storage),
) -> AuthResponse:
    """Authenticate credentials and issue a signed JWT.

    A locked account raises AccountLockedError, which the shared error mapper turns into
    423 Locked carrying `remaining_lockout_seconds`.
    """
    user_doc, token = authenticate_user(
        storage,
        user_id=payload.username,
        password=payload.password,
    )
    return _auth_response(user_doc, token)


@router.post("/forgot-password", response_model=GenericMessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    storage: ResearchStorage = Depends(get_storage),
) -> GenericMessageResponse:
    """Request a password reset link.

    `request_password_reset` is the sole authority here: it performs the account lookup,
    the reset rate limiting, the email dispatch and the anti-enumeration timing floor, and
    returns one identical message whether or not the account exists. This route awaits that
    call in full - it must never short-circuit to a faster response path, since a faster
    reply for a non-existent account is exactly the timing side-channel the floor closes.
    """
    message = request_password_reset(
        storage,
        user_id_or_email=payload.identifier,
        rate_limiter=get_rate_limiter(),
    )
    return GenericMessageResponse(message=message)


@router.post("/reset-password", response_model=GenericMessageResponse)
def reset_password(
    payload: ResetPasswordRequest,
    storage: ResearchStorage = Depends(get_storage),
) -> GenericMessageResponse:
    """Confirm a password reset with a single-use, time-limited token."""
    confirm_password_reset(
        storage,
        token=payload.token,
        new_password=payload.new_password,
        rate_limiter=get_rate_limiter(),
    )
    return GenericMessageResponse(
        message="Password reset successfully! You can now log in with your new password."
    )
