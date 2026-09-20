"""Request and response models for the Phase 7 HTTP API.

These are transport shapes only. All validation that matters (password policy, query
sanitization, quota accounting) is performed by the underlying core modules.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str = Field(..., description="Requested unique username.")
    password: str = Field(..., description="Plain text password (policy enforced by src.auth).")
    email: Optional[str] = Field(default=None, description="Optional email address.")


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    """Issued on successful register/login. Mirrors the CLI flow, which also logs in
    immediately after a successful registration."""
    user_id: str
    email: Optional[str] = None
    access_token: str
    token_type: str = "bearer"
    expires_at: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    identifier: str = Field(..., description="Registered username or email address.")


class GenericMessageResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., description="Single-use password reset token.")
    new_password: str


# --------------------------------------------------------------------------------------
# Quota
# --------------------------------------------------------------------------------------

class PersonalQuota(BaseModel):
    """The requesting identity's own daily/burst allocation."""
    user_id: str
    daily_used: int
    daily_limit: int
    daily_remaining: int
    rpm_used: int
    rpm_limit: int
    rpm_remaining: int
    seconds_to_daily_reset: int
    exhausted: bool


class GlobalQuota(BaseModel):
    """The service-wide shared cap. Exhausting this is a property of the service, not of
    the requesting user, and must be surfaced with different wording."""
    enabled: bool
    used: int
    limit: int
    remaining: int
    exhausted: bool
    seconds_to_daily_reset: int


class QuotaResponse(BaseModel):
    scope: str = Field(..., description="'user' for an authenticated identity, 'guest' otherwise.")
    personal: PersonalQuota
    global_capacity: GlobalQuota = Field(..., alias="global")

    model_config = {"populate_by_name": True}


# --------------------------------------------------------------------------------------
# History
# --------------------------------------------------------------------------------------

class HistoryListItem(BaseModel):
    session_id: str
    query: str
    created_at: str
    source_count: int
    contradiction_count: int
    is_fallback: bool


class HistoryListResponse(BaseModel):
    sessions: List[HistoryListItem]
    total: int


class HistoryDetailResponse(BaseModel):
    session_id: str
    user_id: str
    query: str
    plan: List[str] = Field(default_factory=list)
    report: str
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    summaries: List[Dict[str, Any]] = Field(default_factory=list)
    fact_check: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class DeleteSessionResponse(BaseModel):
    session_id: str
    deleted: bool


# --------------------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """Uniform error envelope.

    `message` always carries the exact text raised by the underlying core module - the API
    layer never rewrites error copy.
    """
    error: str = Field(..., description="Machine-readable error code.")
    message: str = Field(..., description="Human-readable message raised by the core module.")
    retry_after_seconds: Optional[int] = None
    remaining_lockout_seconds: Optional[int] = None
    cap_scope: Optional[str] = Field(
        default=None,
        description="For daily quota errors: 'personal' (this user's allocation) or 'global' (service-wide shared cap).",
    )
