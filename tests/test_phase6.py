"""Phase 6 Unit, Integration, & Security Test Suite.

Tests:
1. Requests-Per-Minute (RPM) Burst Rate Limiting (Sliding 60-second window, retry-after computation).
2. Daily Query Quotas (Cap enforcement, UTC midnight reset).
3. Authentication Brute-Force Defense (Progressive tracking, account lockout after N failed attempts).
4. Per-User Quota Isolation (Zero cross-user quota pollution).
5. Pipeline Gate Interception (Blocks request before Planner or Search are invoked).
"""

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.config import Settings, settings
from src.storage import ResearchStorage
from src.rate_limiter import (
    RateLimiter,
    QuotaStatus,
    RateLimitExceededError,
    DailyLimitExceededError,
    BurstRateLimitExceededError,
    AccountLockedError,
)
from src.auth import register_user, authenticate_user, InvalidCredentialsError
from src.agents.planner_agent import PlanOutput
from src.agents.summarizer_agent import SummaryOutput
from src.agents.fact_checker_agent import FactCheckOutput
from src.pipeline import ResearchPipeline, ResearchResult


class TestBurstRateLimiting(unittest.TestCase):
    """Test requests-per-minute (RPM) burst rate limiting with sliding window."""

    def setUp(self):
        self.storage = ResearchStorage(force_mock=True, db_name="test_rate_db")
        self.limiter = RateLimiter(storage=self.storage)
        self.user = "burst_tester"

    def test_burst_under_limit_succeeds(self):
        # Default RPM limit is 3
        for i in range(settings.requests_per_minute_limit):
            quota = self.limiter.check_and_consume(self.user)
            self.assertEqual(quota.rpm_used, i + 1)
            self.assertEqual(quota.rpm_remaining, settings.requests_per_minute_limit - (i + 1))

    def test_burst_exceeding_limit_raises_burst_error(self):
        # Consume all allowed RPM slots
        for _ in range(settings.requests_per_minute_limit):
            self.limiter.check_and_consume(self.user)

        # The next immediate request must be blocked
        with self.assertRaises(BurstRateLimitExceededError) as ctx:
            self.limiter.check_and_consume(self.user)

        self.assertGreater(ctx.exception.retry_after_seconds, 0)
        self.assertLessEqual(ctx.exception.retry_after_seconds, 60)
        self.assertIn("Requests-per-minute limit reached", str(ctx.exception))

    def test_sliding_window_clears_old_timestamps(self):
        # Populate with 3 requests from 65 seconds ago
        old_time = datetime.now(timezone.utc).timestamp() - 65.0
        record = {
            "user_id": self.user,
            "daily_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "daily_count": 0,
            "minute_timestamps": [old_time, old_time + 1, old_time + 2],
        }
        self.storage.save_rate_limit_record(self.user, record)

        # Request now should succeed as old timestamps are filtered out
        quota = self.limiter.check_and_consume(self.user)
        self.assertEqual(quota.rpm_used, 1)


class TestDailyQueryQuota(unittest.TestCase):
    """Test per-user daily search query quotas."""

    def setUp(self):
        self.storage = ResearchStorage(force_mock=True, db_name="test_daily_db")
        self.limiter = RateLimiter(storage=self.storage)
        self.user = "daily_tester"

    def test_daily_limit_enforced(self):
        # Set daily count at limit
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        record = {
            "user_id": self.user,
            "daily_date": today_str,
            "daily_count": settings.daily_query_limit,
            "minute_timestamps": [],
        }
        self.storage.save_rate_limit_record(self.user, record)

        with self.assertRaises(DailyLimitExceededError) as ctx:
            self.limiter.check_and_consume(self.user)

        self.assertGreater(ctx.exception.retry_after_seconds, 0)
        self.assertIn("Daily research quota reached", str(ctx.exception))

    def test_daily_quota_resets_on_new_day(self):
        yesterday_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        record = {
            "user_id": self.user,
            "daily_date": yesterday_str,
            "daily_count": settings.daily_query_limit,
            "minute_timestamps": [],
        }
        self.storage.save_rate_limit_record(self.user, record)

        # New day should reset daily count to 1
        quota = self.limiter.check_and_consume(self.user)
        self.assertEqual(quota.daily_used, 1)
        self.assertEqual(quota.daily_remaining, settings.daily_query_limit - 1)


class TestLoginLockoutDefense(unittest.TestCase):
    """Test brute-force password guessing defense and temporary account lockout."""

    def setUp(self):
        self.storage = ResearchStorage(force_mock=True, db_name="test_lockout_db")
        self.limiter = RateLimiter(storage=self.storage)
        self.user = "target_user"
        register_user(self.storage, user_id=self.user, password="CorrectPassword123!")

    def test_lockout_after_max_failed_attempts(self):
        # 1 to 4 failed attempts raise InvalidCredentialsError but do not lock
        for attempt in range(1, settings.auth_max_failed_attempts):
            with self.assertRaises(InvalidCredentialsError):
                authenticate_user(self.storage, user_id=self.user, password="WrongPassword")

        # 5th failed attempt triggers lockout
        with self.assertRaises(InvalidCredentialsError):
            authenticate_user(self.storage, user_id=self.user, password="WrongPassword")

        # Now, even with the correct password, login is blocked with AccountLockedError
        with self.assertRaises(AccountLockedError) as ctx:
            authenticate_user(self.storage, user_id=self.user, password="CorrectPassword123!")

        self.assertGreater(ctx.exception.remaining_lockout_seconds, 0)
        self.assertIn("temporarily locked", str(ctx.exception))

    def test_successful_login_resets_failed_count(self):
        # 2 failed attempts
        for _ in range(2):
            with self.assertRaises(InvalidCredentialsError):
                authenticate_user(self.storage, user_id=self.user, password="WrongPassword")

        # Successful login resets the counter
        user_doc, token = authenticate_user(self.storage, user_id=self.user, password="CorrectPassword123!")
        self.assertIsNotNone(token)

        # Check rate limit record directly
        rec = self.storage.get_rate_limit_record(self.user)
        self.assertEqual(rec.get("failed_login_attempts"), 0)
        self.assertIsNone(rec.get("lockout_until"))


class TestPerUserQuotaIsolation(unittest.TestCase):
    """Ensure User A exhausting their quota does not affect User B."""

    def setUp(self):
        self.storage = ResearchStorage(force_mock=True, db_name="test_isolation_db")
        self.limiter = RateLimiter(storage=self.storage)
        self.user_a = "user_alpha"
        self.user_b = "user_beta"

    def test_cross_user_quota_independence(self):
        # User A exhausts daily quota
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.storage.save_rate_limit_record(self.user_a, {
            "user_id": self.user_a,
            "daily_date": today_str,
            "daily_count": settings.daily_query_limit,
            "minute_timestamps": [],
        })

        # User A is blocked
        with self.assertRaises(DailyLimitExceededError):
            self.limiter.check_and_consume(self.user_a)

        # User B can still execute queries normally
        quota_b = self.limiter.check_and_consume(self.user_b)
        self.assertEqual(quota_b.daily_used, 1)
        self.assertEqual(quota_b.daily_remaining, settings.daily_query_limit - 1)


class TestPipelineGateInterception(unittest.TestCase):
    """Test that pipeline intercepts rate-limited requests before calling any LLM or Search API."""

    @patch("src.config.Settings.validate_keys")
    def test_pipeline_blocks_before_planner_or_search(self, mock_validate):
        mock_validate.return_value = None

        mock_planner = MagicMock()
        mock_search = MagicMock()
        mock_storage = ResearchStorage(force_mock=True)
        limiter = RateLimiter(storage=mock_storage)

        # Set user as quota exhausted
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        mock_storage.save_rate_limit_record("exhausted_user", {
            "user_id": "exhausted_user",
            "daily_date": today_str,
            "daily_count": settings.daily_query_limit,
            "minute_timestamps": [],
        })

        pipeline = ResearchPipeline(
            planner_agent=mock_planner,
            search_agent=mock_search,
            storage=mock_storage,
            rate_limiter=limiter,
        )

        with self.assertRaises(DailyLimitExceededError):
            pipeline.run(query="What is quantum computing?", user_id="exhausted_user")

        # Verify zero LLM or Search calls were made!
        mock_planner.plan.assert_not_called()
        mock_search.search_multi.assert_not_called()

    @patch("src.config.Settings.validate_keys")
    def test_invalid_query_does_not_consume_quota(self, mock_validate):
        """Ensure invalid or malicious queries fail fast WITHOUT burning user search allocation."""
        mock_validate.return_value = None
        mock_planner = MagicMock()
        mock_search = MagicMock()
        mock_storage = ResearchStorage(force_mock=True)
        limiter = RateLimiter(storage=mock_storage)

        pipeline = ResearchPipeline(
            planner_agent=mock_planner,
            search_agent=mock_search,
            storage=mock_storage,
            rate_limiter=limiter,
        )

        user = "careful_user"

        # 1. Test empty query fails validation
        with self.assertRaises(ValueError):
            pipeline.run(query="", user_id=user)

        # 2. Test oversized query (>500 chars) fails validation
        oversized = "A" * 501
        with self.assertRaises(ValueError):
            pipeline.run(query=oversized, user_id=user)

        # 3. Assert rate limit record for user still has 0 daily_count
        rec = mock_storage.get_rate_limit_record(user)
        self.assertEqual(rec.get("daily_count", 0), 0)
        self.assertEqual(len(rec.get("minute_timestamps", [])), 0)

    @patch("src.config.Settings.validate_keys")
    def test_guest_session_scoping_avoids_global_lockout(self, mock_validate):
        """Ensure guest mode scoped with session_id isolates quota across unauthenticated sessions."""
        mock_validate.return_value = None
        mock_planner = MagicMock()
        mock_search = MagicMock()
        mock_summarizer = MagicMock()
        mock_fact_checker = MagicMock()
        mock_writer = MagicMock()

        mock_planner.plan.return_value = (PlanOutput(sub_queries=["q1"], rationale="Plan ok"), {})
        mock_search.search_multi.return_value = [{"title": "T", "url": "https://a.com", "content": "C"}]
        mock_summarizer.summarize.return_value = (SummaryOutput(sources=[]), {})
        mock_fact_checker.verify.return_value = (FactCheckOutput(consensus_facts=[], unique_facts=[], contradictions=[]), {})
        mock_writer.synthesize.return_value = ("Report", {})

        mock_storage = ResearchStorage(force_mock=True)
        limiter = RateLimiter(storage=mock_storage)

        pipeline = ResearchPipeline(
            planner_agent=mock_planner,
            search_agent=mock_search,
            summarizer_agent=mock_summarizer,
            fact_checker_agent=mock_fact_checker,
            writer_agent=mock_writer,
            storage=mock_storage,
            rate_limiter=limiter,
        )

        # Guest Session A executes a query
        res_a = pipeline.run(query="Guest question 1", session_id="cli_session_a")
        self.assertEqual(res_a.quota_status.user_id, "guest_cli_session_a")
        self.assertEqual(res_a.quota_status.daily_used, 1)

        # Guest Session B executes a query with independent quota
        res_b = pipeline.run(query="Guest question 2", session_id="cli_session_b")
        self.assertEqual(res_b.quota_status.user_id, "guest_cli_session_b")
        self.assertEqual(res_b.quota_status.daily_used, 1)


class TestGlobalAggregateBudgetProtection(unittest.TestCase):
    """Test global service-wide search query budget protection."""

    def setUp(self):
        self.storage = ResearchStorage(force_mock=True, db_name="test_global_budget_db")
        self.limiter = RateLimiter(storage=self.storage)

    def test_global_aggregate_cap_blocks_when_exhausted(self):
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Simulate global aggregate cap exhausted
        self.storage.save_rate_limit_record("__global_aggregate__", {
            "user_id": "__global_aggregate__",
            "daily_date": today_str,
            "daily_count": settings.global_daily_query_limit,
            "minute_timestamps": [],
        })

        # Even a brand new user with 0 queries must be blocked by global capacity
        with self.assertRaises(DailyLimitExceededError) as ctx:
            self.limiter.check_and_consume("fresh_new_user")

        self.assertIn("Service-wide shared research capacity reached", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
