"""Rate Limiting and User Quota Management Layer (Phase 6).

Implements:
1. Daily Research Query Quota (protects shared Tavily API budget).
2. Requests-Per-Minute (RPM) Burst Rate Limiting (sliding window counter, protects backend/LLM from flooding).
3. Authentication Brute-Force & Credential-Stuffing Defense (progressive lockout on consecutive failed logins).
4. Full telemetry and QuotaStatus reporting.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from src.config import settings
from src.storage import ResearchStorage
from src.logger import get_logger

logger = get_logger(__name__)


class RateLimitExceededError(Exception):
    """Base exception raised when a rate limit or quota is exceeded."""

    def __init__(self, message: str, retry_after_seconds: int = 0, limit_type: str = "general") -> None:
        super().__init__(message)
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        self.limit_type = limit_type


class DailyLimitExceededError(RateLimitExceededError):
    """Raised when user exceeds their daily research query allocation."""

    def __init__(self, message: str, retry_after_seconds: int = 0) -> None:
        super().__init__(message, retry_after_seconds=retry_after_seconds, limit_type="daily")


class BurstRateLimitExceededError(RateLimitExceededError):
    """Raised when user sends requests faster than the allowed requests-per-minute (RPM) limit."""

    def __init__(self, message: str, retry_after_seconds: int = 0) -> None:
        super().__init__(message, retry_after_seconds=retry_after_seconds, limit_type="rpm")


class AccountLockedError(Exception):
    """Raised when an account is temporarily locked due to consecutive failed login attempts."""

    def __init__(self, message: str, remaining_lockout_seconds: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.remaining_lockout_seconds = remaining_lockout_seconds


class QuotaStatus(BaseModel):
    """Telemetry report representing current user quota and burst usage."""
    user_id: str
    daily_used: int
    daily_limit: int
    daily_remaining: int
    rpm_used: int
    rpm_limit: int
    rpm_remaining: int
    seconds_to_daily_reset: int


class RateLimiter:
    """Rate Limiter enforcing daily query caps, burst RPM limits, and login lockout."""

    def __init__(self, storage: Optional[ResearchStorage] = None) -> None:
        self.storage = storage or ResearchStorage()

    def _seconds_until_midnight_utc(self) -> int:
        """Calculate number of seconds remaining until the next 00:00:00 UTC."""
        now = datetime.now(timezone.utc)
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return max(1, int((tomorrow - now).total_seconds()))

    def check_and_consume(self, user_id: str) -> QuotaStatus:
        """Check rate limits and atomically consume one query allocation.

        Args:
            user_id: Unique user identifier.

        Returns:
            QuotaStatus detailing updated usage and remaining capacity.

        Raises:
            BurstRateLimitExceededError: If the requests-per-minute threshold is violated.
            DailyLimitExceededError: If the daily query allocation is exhausted.
        """
        clean_user = user_id.strip() if user_id else "guest"
        record = self.storage.get_rate_limit_record(clean_user)

        now_dt = datetime.now(timezone.utc)
        now_ts = now_dt.timestamp()
        today_str = now_dt.strftime("%Y-%m-%d")

        # 1. Check Burst Rate Limit (Sliding 60-second window)
        raw_timestamps: List[float] = record.get("minute_timestamps", [])
        recent_timestamps = [t for t in raw_timestamps if (now_ts - t) < 60.0]

        if len(recent_timestamps) >= settings.requests_per_minute_limit:
            oldest = min(recent_timestamps)
            retry_after = max(1, int(60.0 - (now_ts - oldest)))
            logger.warning(
                f"Rate limit exceeded (RPM) for user '{clean_user}'. "
                f"Current: {len(recent_timestamps)}/{settings.requests_per_minute_limit} RPM. "
                f"Retry after {retry_after}s."
            )
            raise BurstRateLimitExceededError(
                f"Requests-per-minute limit reached ({settings.requests_per_minute_limit} req/min). "
                f"Please wait {retry_after} second(s) before trying again.",
                retry_after_seconds=retry_after,
            )

        # 2. Check Daily Query Cap
        stored_date = record.get("daily_date", "")
        if stored_date == today_str:
            daily_count = int(record.get("daily_count", 0))
        else:
            daily_count = 0

        if daily_count >= settings.daily_query_limit:
            secs_to_reset = self._seconds_until_midnight_utc()
            hours = secs_to_reset // 3600
            mins = (secs_to_reset % 3600) // 60
            logger.warning(
                f"Daily query quota exceeded for user '{clean_user}'. "
                f"Used: {daily_count}/{settings.daily_query_limit}. Resets in {hours}h {mins}m."
            )
            raise DailyLimitExceededError(
                f"Daily research quota reached ({settings.daily_query_limit} queries/day). "
                f"Quota resets at 00:00 UTC (in {hours}h {mins}m).",
                retry_after_seconds=secs_to_reset,
            )

        # 3. Consume Quota
        daily_count += 1
        recent_timestamps.append(now_ts)

        record["daily_date"] = today_str
        record["daily_count"] = daily_count
        record["minute_timestamps"] = recent_timestamps

        self.storage.save_rate_limit_record(clean_user, record)
        logger.info(
            f"Consumed query quota for user '{clean_user}'. "
            f"Daily: {daily_count}/{settings.daily_query_limit} | "
            f"RPM: {len(recent_timestamps)}/{settings.requests_per_minute_limit}"
        )

        return QuotaStatus(
            user_id=clean_user,
            daily_used=daily_count,
            daily_limit=settings.daily_query_limit,
            daily_remaining=max(0, settings.daily_query_limit - daily_count),
            rpm_used=len(recent_timestamps),
            rpm_limit=settings.requests_per_minute_limit,
            rpm_remaining=max(0, settings.requests_per_minute_limit - len(recent_timestamps)),
            seconds_to_daily_reset=self._seconds_until_midnight_utc(),
        )

    def get_quota_status(self, user_id: str) -> QuotaStatus:
        """Inspect current user quota without consuming an allocation."""
        clean_user = user_id.strip() if user_id else "guest"
        record = self.storage.get_rate_limit_record(clean_user)

        now_dt = datetime.now(timezone.utc)
        now_ts = now_dt.timestamp()
        today_str = now_dt.strftime("%Y-%m-%d")

        raw_timestamps: List[float] = record.get("minute_timestamps", [])
        recent_timestamps = [t for t in raw_timestamps if (now_ts - t) < 60.0]

        stored_date = record.get("daily_date", "")
        if stored_date == today_str:
            daily_count = int(record.get("daily_count", 0))
        else:
            daily_count = 0

        return QuotaStatus(
            user_id=clean_user,
            daily_used=daily_count,
            daily_limit=settings.daily_query_limit,
            daily_remaining=max(0, settings.daily_query_limit - daily_count),
            rpm_used=len(recent_timestamps),
            rpm_limit=settings.requests_per_minute_limit,
            rpm_remaining=max(0, settings.requests_per_minute_limit - len(recent_timestamps)),
            seconds_to_daily_reset=self._seconds_until_midnight_utc(),
        )

    def record_login_attempt(self, user_id: str, success: bool) -> None:
        """Track login attempts to protect against brute-force password guessing."""
        clean_user = user_id.strip() if user_id else "unknown"
        record = self.storage.get_rate_limit_record(clean_user)

        if success:
            record["failed_login_attempts"] = 0
            record["lockout_until"] = None
            logger.info(f"Reset failed login count for user '{clean_user}'.")
        else:
            failed = int(record.get("failed_login_attempts", 0)) + 1
            record["failed_login_attempts"] = failed
            logger.warning(
                f"Recorded failed login attempt {failed}/{settings.auth_max_failed_attempts} for user '{clean_user}'."
            )
            if failed >= settings.auth_max_failed_attempts:
                lockout_time = datetime.now(timezone.utc) + timedelta(minutes=settings.auth_lockout_minutes)
                record["lockout_until"] = lockout_time
                logger.warning(
                    f"Account '{clean_user}' locked until {lockout_time.isoformat()} "
                    f"({settings.auth_lockout_minutes} mins lockout)."
                )

        self.storage.save_rate_limit_record(clean_user, record)

    def check_login_lockout(self, user_id: str) -> Optional[int]:
        """Check if an account is currently locked out.

        Returns:
            Remaining lockout duration in seconds if locked, or None if clear.
        """
        clean_user = user_id.strip() if user_id else "unknown"
        record = self.storage.get_rate_limit_record(clean_user)

        lockout_until = record.get("lockout_until")
        if not lockout_until:
            return None

        now = datetime.now(timezone.utc)
        if isinstance(lockout_until, str):
            try:
                lockout_until = datetime.fromisoformat(lockout_until)
            except Exception:
                return None

        # Ensure timezone-aware
        if lockout_until.tzinfo is None:
            lockout_until = lockout_until.replace(tzinfo=timezone.utc)

        if now < lockout_until:
            remaining = max(1, int((lockout_until - now).total_seconds()))
            return remaining

        # Lockout period has elapsed: clear lockout state
        record["failed_login_attempts"] = 0
        record["lockout_until"] = None
        self.storage.save_rate_limit_record(clean_user, record)
        return None

    def reset_quota(self, user_id: str) -> None:
        """Reset all rate limits and quotas for a user (administrative helper)."""
        clean_user = user_id.strip() if user_id else "guest"
        record = {
            "user_id": clean_user,
            "daily_date": "",
            "daily_count": 0,
            "minute_timestamps": [],
            "failed_login_attempts": 0,
            "lockout_until": None,
        }
        self.storage.save_rate_limit_record(clean_user, record)
        logger.info(f"Reset rate limits and quotas for user '{clean_user}'.")
