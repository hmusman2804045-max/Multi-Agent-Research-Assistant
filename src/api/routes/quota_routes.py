"""Quota telemetry route.

Reports the two structurally different daily caps separately, because they mean different
things to the user:
  * personal - this identity has spent its own DAILY_QUERY_LIMIT allocation.
  * global   - the shared, service-wide GLOBAL_DAILY_QUERY_LIMIT pool is empty for everyone.
Both are read (never consumed) from `src.rate_limiter`.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from src.api.deps import get_guest_id, get_optional_identity, get_rate_limiter
from src.api.schemas import GlobalQuota, PersonalQuota, QuotaResponse
from src.auth import UserIdentity
from src.pipeline import resolve_rate_limit_identity
from src.rate_limiter import RateLimiter

router = APIRouter(tags=["quota"])


@router.get("/quota", response_model=QuotaResponse, response_model_by_alias=True)
def get_quota(
    identity: Optional[UserIdentity] = Depends(get_optional_identity),
    guest_id: Optional[str] = Depends(get_guest_id),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> QuotaResponse:
    """Report the caller's personal quota alongside the shared service-wide cap.

    Guests may call this with their scoped guest id; the same identity resolution the
    pipeline uses is applied, so the numbers shown are the numbers that will be enforced.
    """
    user_id = identity.user_id if identity else None
    effective_id = resolve_rate_limit_identity(user_id, guest_id)

    personal_status = limiter.get_quota_status(effective_id)
    global_status = limiter.get_global_quota_status()

    return QuotaResponse(
        scope="user" if identity else "guest",
        personal=PersonalQuota(
            **personal_status.model_dump(),
            exhausted=personal_status.daily_remaining <= 0,
        ),
        **{"global": GlobalQuota(**global_status)},
    )
