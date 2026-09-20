"""Phase 5 Unit & Security Test Suite.

Tests:
1. Authentication & JWT Token Security (Signature verification, expiration, tampering, algorithm restriction).
2. Per-User Dual-Key MongoDB/MongoMock Storage (Lesson 5: Isolation, prevention of IDOR / cross-user data leakage).
3. End-to-End Pipeline Integration with User Session Persistence.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import jwt

from src.config import settings
from src.auth import (
    create_access_token,
    verify_access_token,
    UserIdentity,
    AuthError,
    TokenExpiredError,
    InvalidTokenError,
)
from src.storage import ResearchStorage, ResearchSessionDocument
from src.pipeline import ResearchPipeline, ResearchResult
from src.agents.planner_agent import PlanOutput
from src.agents.summarizer_agent import SummaryOutput, SourceSummary
from src.agents.fact_checker_agent import FactCheckOutput, ConsensusFact


class TestJWTAuthentication(unittest.TestCase):
    """Test JWT creation, claim validation, signature enforcement, and tampering defenses."""

    def setUp(self):
        self.secret = "test-secret-key-that-is-at-least-32-chars-long!"
        self.algo = "HS256"

    def test_valid_token_creation_and_verification(self):
        token = create_access_token(
            user_id="alice_researcher",
            session_id="sess_001",
            email="alice@example.com",
            secret_key=self.secret,
            algorithm=self.algo,
        )
        self.assertIsInstance(token, str)

        identity = verify_access_token(
            token,
            secret_key=self.secret,
            algorithm=self.algo,
        )
        self.assertIsInstance(identity, UserIdentity)
        self.assertEqual(identity.user_id, "alice_researcher")
        self.assertEqual(identity.session_id, "sess_001")
        self.assertEqual(identity.email, "alice@example.com")
        self.assertIsNotNone(identity.expires_at)
        self.assertIsNotNone(identity.issued_at)

    def test_expired_token_raises_token_expired_error(self):
        # Create token that expired 10 minutes ago
        token = create_access_token(
            user_id="bob",
            expires_delta=timedelta(minutes=-10),
            secret_key=self.secret,
            algorithm=self.algo,
        )
        with self.assertRaises(TokenExpiredError):
            verify_access_token(token, secret_key=self.secret, algorithm=self.algo)

    def test_tampered_token_signature_raises_invalid_token_error(self):
        token = create_access_token(
            user_id="charlie",
            secret_key=self.secret,
            algorithm=self.algo,
        )
        # Tamper with the token signature (modify last characters)
        tampered_token = token[:-4] + "AAAA"
        with self.assertRaises(InvalidTokenError):
            verify_access_token(tampered_token, secret_key=self.secret, algorithm=self.algo)

    def test_wrong_secret_key_raises_invalid_token_error(self):
        token = create_access_token(
            user_id="dave",
            secret_key=self.secret,
            algorithm=self.algo,
        )
        wrong_secret = "completely-different-wrong-secret-key-32-chars!"
        with self.assertRaises(InvalidTokenError):
            verify_access_token(token, secret_key=wrong_secret, algorithm=self.algo)

    def test_reject_none_algorithm_bypass_attack(self):
        # Craft an unsigned token with alg='none'
        payload = {
            "sub": "attacker",
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        # Encode with none algorithm
        none_token = jwt.encode(payload, key="", algorithm="none")
        with self.assertRaises(InvalidTokenError):
            verify_access_token(none_token, secret_key=self.secret, algorithm=self.algo)

    def test_empty_user_id_rejected(self):
        with self.assertRaises(ValueError):
            create_access_token(user_id="   ")

    def test_prohibited_characters_in_user_id(self):
        with self.assertRaises(ValueError):
            UserIdentity(user_id="admin\0malicious")
        with self.assertRaises(ValueError):
            UserIdentity(user_id="user$injection")


class TestPerUserStorageIsolation(unittest.TestCase):
    """Test strict per-user dual-key storage isolation (PRD Lesson 5)."""

    def setUp(self):
        # Force in-memory MongoMock for hermetic, fast testing
        self.storage = ResearchStorage(force_mock=True, db_name="test_db")
        self.user_a = "user_alpha"
        self.user_b = "user_beta"

    def test_save_and_retrieve_session(self):
        doc = ResearchSessionDocument(
            session_id="session_100",
            user_id=self.user_a,
            query="Quantum Computing Breakthroughs",
            plan=["Subquery 1", "Subquery 2"],
            sources=[{"url": "https://example.com/q1", "title": "Quantum 1"}],
            report="Comprehensive quantum report.",
        )
        saved_id = self.storage.save_session(doc)
        self.assertEqual(saved_id, "session_100")

        retrieved = self.storage.get_session(user_id=self.user_a, session_id="session_100")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.user_id, self.user_a)
        self.assertEqual(retrieved.session_id, "session_100")
        self.assertEqual(retrieved.query, "Quantum Computing Breakthroughs")
        self.assertEqual(retrieved.report, "Comprehensive quantum report.")

    def test_dual_key_isolation_cross_user_read_prevention(self):
        """User B MUST NOT be able to read User A's session even with the exact session_id."""
        doc_a = ResearchSessionDocument(
            session_id="secret_session_a",
            user_id=self.user_a,
            query="Confidential Research for User Alpha",
            report="Top secret findings.",
        )
        self.storage.save_session(doc_a)

        # User A can read it
        retrieved_a = self.storage.get_session(user_id=self.user_a, session_id="secret_session_a")
        self.assertIsNotNone(retrieved_a)

        # User B cannot read it
        retrieved_b = self.storage.get_session(user_id=self.user_b, session_id="secret_session_a")
        self.assertIsNone(retrieved_b)

    def test_dual_key_isolation_cross_user_delete_prevention(self):
        """User B MUST NOT be able to delete User A's session."""
        doc_a = ResearchSessionDocument(
            session_id="session_to_protect",
            user_id=self.user_a,
            query="Alpha Report",
            report="Protected report.",
        )
        self.storage.save_session(doc_a)

        # User B attempts to delete User A's session
        deleted = self.storage.delete_session(user_id=self.user_b, session_id="session_to_protect")
        self.assertFalse(deleted)

        # User A's session must still exist intact
        still_exists = self.storage.get_session(user_id=self.user_a, session_id="session_to_protect")
        self.assertIsNotNone(still_exists)

    def test_list_user_sessions_only_returns_owners_data(self):
        # Create 3 sessions for User A and 2 for User B
        for i in range(3):
            self.storage.save_session(ResearchSessionDocument(
                session_id=f"sess_a_{i}",
                user_id=self.user_a,
                query=f"Alpha Query {i}",
            ))
        for j in range(2):
            self.storage.save_session(ResearchSessionDocument(
                session_id=f"sess_b_{j}",
                user_id=self.user_b,
                query=f"Beta Query {j}",
            ))

        sessions_a = self.storage.list_user_sessions(user_id=self.user_a)
        self.assertEqual(len(sessions_a), 3)
        for s in sessions_a:
            self.assertEqual(s.user_id, self.user_a)

        sessions_b = self.storage.list_user_sessions(user_id=self.user_b)
        self.assertEqual(len(sessions_b), 2)
        for s in sessions_b:
            self.assertEqual(s.user_id, self.user_b)

    def test_delete_session_success_for_owner(self):
        doc = ResearchSessionDocument(
            session_id="session_del",
            user_id=self.user_a,
            query="Query to delete",
        )
        self.storage.save_session(doc)
        self.assertTrue(self.storage.delete_session(user_id=self.user_a, session_id="session_del"))
        self.assertIsNone(self.storage.get_session(user_id=self.user_a, session_id="session_del"))

    def test_key_sanitization(self):
        with self.assertRaises(ValueError):
            self.storage.get_session(user_id="bad\0user", session_id="sess1")
        with self.assertRaises(ValueError):
            self.storage.get_session(user_id="user1", session_id="sess$injection")
        with self.assertRaises(ValueError):
            self.storage.get_session(user_id="", session_id="sess1")


class TestPipelineSessionPersistence(unittest.TestCase):
    """Test full pipeline integration with Phase 5 storage and user isolation."""

    @patch("src.config.Settings.validate_keys")
    def test_pipeline_persists_session_for_authenticated_user(self, mock_validate):
        mock_validate.return_value = None

        mock_planner = MagicMock()
        mock_planner.plan.return_value = (
            PlanOutput(sub_queries=["Sub 1", "Sub 2"], rationale="Plan ok"),
            {"total_tokens": 50},
        )

        mock_search = MagicMock()
        mock_search.search_multi.return_value = [
            {"title": "Source 1", "url": "https://example.com/1", "content": "Content 1"}
        ]

        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = (
            SummaryOutput(
                sources=[SourceSummary(source_id=1, url="https://example.com/1", key_claims=["Claim 1"])]
            ),
            {"total_tokens": 100},
        )

        mock_fact_checker = MagicMock()
        mock_fact_checker.verify.return_value = (
            FactCheckOutput(
                consensus_facts=[ConsensusFact(fact="Consensus 1", supporting_sources=[1])]
            ),
            {"total_tokens": 80},
        )

        mock_writer = MagicMock()
        mock_writer.synthesize.return_value = (
            "# Final Report\n\nVerified findings [1].",
            {"total_tokens": 150, "model": "test-model"},
        )

        mock_storage = ResearchStorage(force_mock=True)

        pipeline = ResearchPipeline(
            planner_agent=mock_planner,
            search_agent=mock_search,
            summarizer_agent=mock_summarizer,
            fact_checker_agent=mock_fact_checker,
            writer_agent=mock_writer,
            storage=mock_storage,
        )

        result = pipeline.run(
            query="What are the latest developments in Fusion Energy?",
            user_id="scientist_42",
            session_id="custom_session_999",
        )

        self.assertEqual(result.user_id, "scientist_42")
        self.assertEqual(result.session_id, "custom_session_999")
        self.assertIn("Final Report", result.report)

        # Verify it was saved to storage
        saved_doc = mock_storage.get_session(user_id="scientist_42", session_id="custom_session_999")
        self.assertIsNotNone(saved_doc)
        self.assertEqual(saved_doc.user_id, "scientist_42")
        self.assertEqual(saved_doc.session_id, "custom_session_999")
        self.assertEqual(saved_doc.query, "What are the latest developments in Fusion Energy?")
        self.assertIn("Final Report", saved_doc.report)
        self.assertEqual(len(saved_doc.sources), 1)

        # Ensure cross-user isolation: another user cannot access it
        other_user_doc = mock_storage.get_session(user_id="other_user", session_id="custom_session_999")
        self.assertIsNone(other_user_doc)


if __name__ == "__main__":
    unittest.main()
