"""Unit and Security Test Suite for Password Reset Subsystem.

Tests:
1. Token Lifecycle & Expiration (Creation, 15-minute TTL, field validation).
2. End-to-End Password Reset Flow (Request -> Confirm -> Verify new credentials work, old credentials fail).
3. Expired & Already-Used Token Rejection (TokenExpiredError, InvalidTokenError).
4. Anti-User Enumeration Defense (Identical generic response for existing vs non-existent accounts).
5. Password Reset Request Rate Limiting (3 requests/hour per identifier).
6. Lockout Auto-Clearing (Password reset unlocks accounts locked by brute-force defense).
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.config import settings
from src.storage import ResearchStorage, PasswordResetToken
from src.auth import (
    register_user,
    authenticate_user,
    request_password_reset,
    confirm_password_reset,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenExpiredError,
    WeakPasswordError,
)
from src.rate_limiter import RateLimiter, RateLimitExceededError, AccountLockedError
from src.email_service import send_password_reset_email


class TestTokenGenerationAndExpiry(unittest.TestCase):
    """Test PasswordResetToken model validation and storage persistence."""

    def setUp(self):
        self.storage = ResearchStorage(force_mock=True, db_name="test_pwd_reset_db")

    def test_token_model_validation(self):
        now_dt = datetime.now(timezone.utc)
        exp_dt = now_dt + timedelta(minutes=15)
        token_doc = PasswordResetToken(
            token="secure_random_token_123",
            user_id="alice",
            created_at=now_dt,
            expires_at=exp_dt,
            used=False,
        )
        self.assertEqual(token_doc.user_id, "alice")
        self.assertEqual(token_doc.token, "secure_random_token_123")
        self.assertFalse(token_doc.used)

    def test_token_storage_crud(self):
        now_dt = datetime.now(timezone.utc)
        exp_dt = now_dt + timedelta(minutes=15)
        token_doc = PasswordResetToken(
            token="sample_token_xyz",
            user_id="bob",
            created_at=now_dt,
            expires_at=exp_dt,
            used=False,
        )
        self.storage.save_reset_token(token_doc)

        retrieved = self.storage.get_reset_token("sample_token_xyz")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.user_id, "bob")
        self.assertFalse(retrieved.used)

        # Mark token as used
        self.storage.mark_reset_token_used("sample_token_xyz")
        updated = self.storage.get_reset_token("sample_token_xyz")
        self.assertTrue(updated.used)


class TestPasswordResetFlow(unittest.TestCase):
    """Test complete end-to-end password reset lifecycle."""

    def setUp(self):
        self.storage = ResearchStorage(force_mock=True, db_name="test_reset_flow_db")
        self.limiter = RateLimiter(storage=self.storage)
        self.user_id = "researcher_dan"
        self.email = "dan@example.com"
        self.old_password = "OldInitialPassword123!"
        self.new_password = "NewSecurePassword456@"
        register_user(self.storage, user_id=self.user_id, password=self.old_password, email=self.email)

    @patch("src.auth.send_password_reset_email")
    def test_successful_password_reset_flow(self, mock_send_email):
        mock_send_email.return_value = True

        # 1. User requests password reset
        msg = request_password_reset(self.storage, self.user_id, rate_limiter=self.limiter)
        self.assertIn("password reset email has been sent", msg)
        mock_send_email.assert_called_once()

        # Extract generated token from storage for testing
        doc = self.storage.reset_tokens_col.find_one({"user_id": self.user_id})
        self.assertIsNotNone(doc)
        token = doc["token"]

        # 2. User confirms password reset with valid token and new password
        success = confirm_password_reset(self.storage, token=token, new_password=self.new_password, rate_limiter=self.limiter)
        self.assertTrue(success)

        # 3. Verify old password no longer works
        with self.assertRaises(InvalidCredentialsError):
            authenticate_user(self.storage, user_id=self.user_id, password=self.old_password)

        # 4. Verify new password successfully authenticates
        user_doc, auth_token = authenticate_user(self.storage, user_id=self.user_id, password=self.new_password)
        self.assertIsNotNone(auth_token)
        self.assertEqual(user_doc.user_id, self.user_id)


class TestExpiredAndUsedTokenRejection(unittest.TestCase):
    """Test rejection of invalid, expired, and already-used reset tokens."""

    def setUp(self):
        self.storage = ResearchStorage(force_mock=True, db_name="test_token_rejection_db")
        self.limiter = RateLimiter(storage=self.storage)
        self.user_id = "eva_user"
        register_user(self.storage, user_id=self.user_id, password="OriginalPassword123!", email="eva@example.com")

    def test_non_existent_token_rejected(self):
        with self.assertRaises(InvalidTokenError) as ctx:
            confirm_password_reset(self.storage, token="fake_non_existent_token", new_password="NewPassword123!")
        self.assertIn("Invalid or non-existent", str(ctx.exception))

    def test_expired_token_rejected(self):
        # Create an expired token (16 minutes ago)
        old_time = datetime.now(timezone.utc) - timedelta(minutes=16)
        expired_token = PasswordResetToken(
            token="expired_token_abc",
            user_id=self.user_id,
            created_at=old_time - timedelta(minutes=15),
            expires_at=old_time,
            used=False,
        )
        self.storage.save_reset_token(expired_token)

        with self.assertRaises(TokenExpiredError) as ctx:
            confirm_password_reset(self.storage, token="expired_token_abc", new_password="NewPassword123!")
        self.assertIn("expired", str(ctx.exception))

    def test_already_used_token_rejected(self):
        now_dt = datetime.now(timezone.utc)
        used_token = PasswordResetToken(
            token="used_token_def",
            user_id=self.user_id,
            created_at=now_dt,
            expires_at=now_dt + timedelta(minutes=15),
            used=True,
        )
        self.storage.save_reset_token(used_token)

        with self.assertRaises(InvalidTokenError) as ctx:
            confirm_password_reset(self.storage, token="used_token_def", new_password="NewPassword123!")
        self.assertIn("already been used", str(ctx.exception))


class TestUserEnumerationPrevention(unittest.TestCase):
    """Test that password reset endpoint never leaks user existence."""

    def setUp(self):
        self.storage = ResearchStorage(force_mock=True, db_name="test_anti_enum_db")
        self.limiter = RateLimiter(storage=self.storage)
        register_user(self.storage, user_id="real_user", password="RealPassword123!", email="real@example.com")

    @patch("src.auth.send_password_reset_email")
    def test_identical_response_for_existing_and_non_existing_users(self, mock_send_email):
        mock_send_email.return_value = True

        res_real = request_password_reset(self.storage, "real_user", rate_limiter=self.limiter)
        res_fake = request_password_reset(self.storage, "ghost_non_existent_user", rate_limiter=self.limiter)

        self.assertEqual(res_real, res_fake)
        self.assertEqual(res_real, "If an account with that identifier exists, a password reset email has been sent.")


class TestPasswordResetRateLimiting(unittest.TestCase):
    """Test rate limiting on password reset requests (e.g. 3 requests/hour)."""

    def setUp(self):
        self.storage = ResearchStorage(force_mock=True, db_name="test_reset_rate_limit_db")
        self.limiter = RateLimiter(storage=self.storage)
        self.target = "targeted_user"
        register_user(self.storage, user_id=self.target, password="TargetPassword123!", email="target@example.com")

    @patch("src.auth.send_password_reset_email")
    def test_reset_requests_capped_at_limit_per_hour(self, mock_send_email):
        mock_send_email.return_value = True

        # First 3 requests succeed
        for _ in range(settings.password_reset_limit_per_hour):
            request_password_reset(self.storage, self.target, rate_limiter=self.limiter)

        # 4th request must be rate limited
        with self.assertRaises(RateLimitExceededError) as ctx:
            request_password_reset(self.storage, self.target, rate_limiter=self.limiter)

        self.assertGreater(ctx.exception.retry_after_seconds, 0)
        self.assertIn("Too many password reset requests", str(ctx.exception))


class TestLockoutAutoResetOnPasswordReset(unittest.TestCase):
    """Test that successful password reset clears account lockout from failed logins."""

    def setUp(self):
        self.storage = ResearchStorage(force_mock=True, db_name="test_lockout_clear_db")
        self.limiter = RateLimiter(storage=self.storage)
        self.user_id = "locked_user"
        self.old_password = "InitialPassword123!"
        self.new_password = "BrandNewPassword456@"
        register_user(self.storage, user_id=self.user_id, password=self.old_password, email="locked@example.com")

    def test_password_reset_clears_account_lockout(self):
        # 1. Trigger account lockout with 5 wrong attempts
        for _ in range(settings.auth_max_failed_attempts):
            with self.assertRaises(InvalidCredentialsError):
                authenticate_user(self.storage, user_id=self.user_id, password="WrongPassword!")

        # Confirm account is locked
        with self.assertRaises(AccountLockedError):
            authenticate_user(self.storage, user_id=self.user_id, password=self.old_password)

        # 2. Issue password reset token and reset password
        now_dt = datetime.now(timezone.utc)
        token_doc = PasswordResetToken(
            token="unlock_token_123",
            user_id=self.user_id,
            created_at=now_dt,
            expires_at=now_dt + timedelta(minutes=15),
            used=False,
        )
        self.storage.save_reset_token(token_doc)

        confirm_password_reset(self.storage, token="unlock_token_123", new_password=self.new_password, rate_limiter=self.limiter)

        # 3. Account must now be unlocked and authenticate successfully with new password
        user_doc, token = authenticate_user(self.storage, user_id=self.user_id, password=self.new_password)
        self.assertIsNotNone(token)
        self.assertEqual(user_doc.user_id, self.user_id)


if __name__ == "__main__":
    unittest.main()
