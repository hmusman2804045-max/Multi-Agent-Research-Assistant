"""Phase 7 Web API Integration Test Suite.

Tests the thin FastAPI layer that exposes the existing core modules over HTTP:

1. Auth flows (register, login, forgot-password anti-enumeration, reset-password).
2. Account lockout surfacing as 423 with remaining_lockout_seconds.
3. Both rate-limit types: personal daily cap, service-wide global cap, and RPM burst,
   including the personal/global discriminator the frontend needs.
4. SSE research stream emitting the expected 5-event step sequence, for both an
   authenticated user and an unauthenticated guest.
5. History endpoints and their dual-key per-user isolation over HTTP.

Every test uses a hermetically isolated in-memory storage fixture and fully mocked agents:
no network, no LLM, and no real search calls are made.
"""

import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.agents.fact_checker_agent import Contradiction, FactCheckOutput
from src.agents.planner_agent import PlanOutput
from src.agents.summarizer_agent import SourceSummary, SummaryOutput
from src.api import deps
from src.api.app import create_app
from src.auth import create_access_token
from src.config import settings
from src.pipeline import PIPELINE_STEPS, ResearchPipeline
from src.rate_limiter import RateLimiter
from src.storage import PasswordResetToken, ResearchStorage

USAGE = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30, "model": "test-model"}


def build_mock_pipeline(storage: ResearchStorage, contradictions: bool = False) -> ResearchPipeline:
    """Construct a ResearchPipeline whose five agents are fully mocked."""
    planner = MagicMock()
    planner.plan.return_value = (
        PlanOutput(
            sub_queries=["sub query one", "sub query two"],
            rationale="covers both angles",
            is_fallback=False,
        ),
        USAGE,
    )

    search = MagicMock()
    search.search_multi.return_value = [
        {"title": "Source A", "url": "https://a.example.com/a", "content": "alpha content", "score": 0.9},
        {"title": "Source B", "url": "https://b.example.com/b", "content": "beta content", "score": 0.8},
        {"title": "Source C", "url": "https://c.example.com/c", "content": "gamma content", "score": 0.7},
    ]

    summarizer = MagicMock()
    summarizer.summarize.return_value = (
        SummaryOutput(
            sources=[
                SourceSummary(
                    source_id=1, title="Source A", url="https://a.example.com/a",
                    key_claims=["claim one", "claim two"], summary="a summary",
                ),
                SourceSummary(
                    source_id=2, title="Source B", url="https://b.example.com/b",
                    key_claims=["claim three"], summary="b summary",
                ),
            ],
            is_fallback=False,
        ),
        USAGE,
    )

    fact_checker = MagicMock()
    fact_checker.verify.return_value = (
        FactCheckOutput(
            consensus_facts=[],
            unique_facts=[],
            contradictions=(
                [Contradiction(topic="dates", conflict="A says 2020, B says 2021", conflicting_sources=[1, 2])]
                if contradictions else []
            ),
            verification_summary="mostly aligned",
            is_fallback=False,
        ),
        USAGE,
    )

    writer = MagicMock()
    writer.synthesize.return_value = ("## Summary\n\nFindings with citation [1] and [2].", USAGE)

    with patch("src.config.Settings.validate_keys", return_value=None):
        return ResearchPipeline(
            planner_agent=planner,
            search_agent=search,
            summarizer_agent=summarizer,
            fact_checker_agent=fact_checker,
            writer_agent=writer,
            storage=storage,
            rate_limiter=RateLimiter(storage=storage),
        )


def parse_sse(body: str) -> List[dict]:
    """Parse a raw SSE response body into a list of {event, data} dicts."""
    events = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        event_name, data_lines = None, []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if event_name:
            events.append({
                "event": event_name,
                "data": json.loads("".join(data_lines)) if data_lines else {},
            })
    return events


class ApiTestCase(unittest.TestCase):
    """Base fixture wiring the app to isolated in-memory storage and mocked agents."""

    contradictions = False

    def setUp(self):
        self.storage = ResearchStorage(force_mock=True, db_name=f"test_api_{self.id()}")
        self.pipeline = build_mock_pipeline(self.storage, contradictions=self.contradictions)
        deps.reset_state(storage=self.storage, pipeline=self.pipeline)
        self.app = create_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def tearDown(self):
        deps.reset_state()

    # -- helpers ----------------------------------------------------------------------
    def register(self, username="tester", password="testerpass123", email=None):
        return self.client.post(
            "/api/auth/register",
            json={"username": username, "password": password, "email": email},
        )

    def token_for(self, username="tester", password="testerpass123", email=None) -> str:
        resp = self.register(username, password, email)
        self.assertEqual(resp.status_code, 201, resp.text)
        return resp.json()["access_token"]

    @staticmethod
    def auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def exhaust_daily(self, user_id: str):
        """Mark a user's personal daily allocation as fully spent."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.storage.save_rate_limit_record(user_id, {
            "user_id": user_id,
            "daily_date": today,
            "daily_count": settings.daily_query_limit,
            "minute_timestamps": [],
        })

    def exhaust_global(self):
        """Mark the shared service-wide daily pool as fully spent."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.storage.save_rate_limit_record("__global_aggregate__", {
            "user_id": "__global_aggregate__",
            "daily_date": today,
            "daily_count": settings.global_daily_query_limit,
            "minute_timestamps": [],
        })

    def stream_research(self, **kwargs):
        with self.client.stream("GET", "/api/research/stream", **kwargs) as resp:
            body = "".join(resp.iter_text())
            return resp, parse_sse(body)

    def run_research(self, token: str, query: str) -> str:
        _, events = self.stream_research(params={"query": query}, headers=self.auth(token))
        return events[-1]["data"]["session_id"]


class TestAuthRoutes(ApiTestCase):
    """Auth endpoints wrap src.auth without reimplementing any of it."""

    def test_register_returns_token_and_identity(self):
        resp = self.register("alice", "alicepass123", "alice@example.com")
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["user_id"], "alice")
        self.assertEqual(body["email"], "alice@example.com")
        self.assertEqual(body["token_type"], "bearer")
        self.assertTrue(body["access_token"])

    def test_register_duplicate_username_returns_409(self):
        self.register("alice", "alicepass123")
        resp = self.register("alice", "alicepass123")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["error"], "user_already_exists")
        # Message is the one raised by src.auth, not new API copy.
        self.assertIn("already exists", resp.json()["message"])

    def test_register_weak_password_returns_400(self):
        resp = self.register("alice", "short")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "weak_password")
        self.assertIn("at least 8 characters", resp.json()["message"])

    def test_login_success_issues_usable_token(self):
        self.register("alice", "alicepass123")
        resp = self.client.post("/api/auth/login", json={"username": "alice", "password": "alicepass123"})
        self.assertEqual(resp.status_code, 200)
        token = resp.json()["access_token"]
        self.assertEqual(self.client.get("/api/history", headers=self.auth(token)).status_code, 200)

    def test_login_wrong_password_returns_401(self):
        self.register("alice", "alicepass123")
        resp = self.client.post("/api/auth/login", json={"username": "alice", "password": "wrongpass123"})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"], "invalid_credentials")

    def test_repeated_failed_logins_lock_account_with_423(self):
        self.register("alice", "alicepass123")
        for _ in range(settings.auth_max_failed_attempts):
            self.client.post("/api/auth/login", json={"username": "alice", "password": "wrongpass123"})

        resp = self.client.post("/api/auth/login", json={"username": "alice", "password": "alicepass123"})
        self.assertEqual(resp.status_code, 423)
        body = resp.json()
        self.assertEqual(body["error"], "account_locked")
        self.assertGreater(body["remaining_lockout_seconds"], 0)
        # Wording must attribute the lock to failed logins specifically.
        self.assertIn("failed login attempts", body["message"])
        self.assertIn("Retry-After", resp.headers)

    def test_forgot_password_is_identical_for_existing_and_missing_accounts(self):
        self.register("alice", "alicepass123", "alice@example.com")

        existing = self.client.post("/api/auth/forgot-password", json={"identifier": "alice"})
        missing = self.client.post("/api/auth/forgot-password", json={"identifier": "ghost_user"})

        self.assertEqual(existing.status_code, 200)
        self.assertEqual(missing.status_code, 200)
        self.assertEqual(existing.json(), missing.json())
        self.assertIn("If an account with that identifier exists", existing.json()["message"])

    def test_forgot_password_preserves_timing_floor(self):
        """The route must not bypass the anti-enumeration timing floor with a fast path."""
        floor = settings.password_reset_timing_floor_seconds
        if floor <= 0:
            self.skipTest("timing floor disabled in this configuration")

        start = time.monotonic()
        self.client.post("/api/auth/forgot-password", json={"identifier": "definitely_missing"})
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, floor)

    def test_forgot_password_rate_limited_returns_429(self):
        for _ in range(settings.password_reset_limit_per_hour):
            self.client.post("/api/auth/forgot-password", json={"identifier": "alice"})
        resp = self.client.post("/api/auth/forgot-password", json={"identifier": "alice"})
        self.assertEqual(resp.status_code, 429)
        self.assertGreater(resp.json()["retry_after_seconds"], 0)

    def test_reset_password_round_trip(self):
        self.register("alice", "alicepass123", "alice@example.com")
        self.storage.save_reset_token(PasswordResetToken(
            token="valid-reset-token",
            user_id="alice",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        ))

        resp = self.client.post("/api/auth/reset-password", json={
            "token": "valid-reset-token", "new_password": "brandnewpass123",
        })
        self.assertEqual(resp.status_code, 200)

        login = self.client.post("/api/auth/login", json={"username": "alice", "password": "brandnewpass123"})
        self.assertEqual(login.status_code, 200)

        # Single use: replaying the same token must fail.
        replay = self.client.post("/api/auth/reset-password", json={
            "token": "valid-reset-token", "new_password": "anotherpass123",
        })
        self.assertEqual(replay.status_code, 401)
        self.assertIn("already been used", replay.json()["message"])

    def test_reset_password_expired_token_returns_401(self):
        """An elapsed 15-minute window maps to 401 token_expired.

        The reset_tokens collection carries a TTL index on expires_at, so an already-past
        token is swept from storage rather than retrievable; the expiry branch is exercised
        by returning a stale document from the lookup directly.
        """
        self.register("alice", "alicepass123", "alice@example.com")
        stale = PasswordResetToken(
            token="stale-token",
            user_id="alice",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        with patch.object(self.storage, "get_reset_token", return_value=stale):
            resp = self.client.post("/api/auth/reset-password", json={
                "token": "stale-token", "new_password": "brandnewpass123",
            })
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"], "token_expired")
        self.assertIn("15-minute window elapsed", resp.json()["message"])

    def test_reset_password_unknown_token_returns_401(self):
        resp = self.client.post("/api/auth/reset-password", json={
            "token": "never-issued-token", "new_password": "brandnewpass123",
        })
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"], "invalid_token")

    def test_expired_access_token_is_rejected(self):
        expired = create_access_token(user_id="alice", expires_delta=timedelta(seconds=-10))
        resp = self.client.get("/api/history", headers=self.auth(expired))
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"], "token_expired")

    def test_forged_token_is_rejected(self):
        forged = create_access_token(user_id="alice", secret_key="an-attacker-controlled-secret-key")
        resp = self.client.get("/api/history", headers=self.auth(forged))
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["error"], "invalid_token")


class TestQuotaRoute(ApiTestCase):
    """The /quota endpoint must keep the personal and global caps distinct."""

    def test_quota_for_authenticated_user(self):
        token = self.token_for("alice", "alicepass123")
        body = self.client.get("/api/quota", headers=self.auth(token)).json()

        self.assertEqual(body["scope"], "user")
        self.assertEqual(body["personal"]["user_id"], "alice")
        self.assertEqual(body["personal"]["daily_limit"], settings.daily_query_limit)
        self.assertFalse(body["personal"]["exhausted"])
        self.assertGreater(body["personal"]["seconds_to_daily_reset"], 0)

    def test_quota_for_guest_uses_scoped_guest_bucket(self):
        body = self.client.get("/api/quota", params={"session_id": "guest_web_abc123"}).json()
        self.assertEqual(body["scope"], "guest")
        self.assertEqual(body["personal"]["user_id"], "guest_web_abc123")

    def test_guest_quota_is_namespaced_away_from_real_users(self):
        """A guest passing a real username must not read that user's allocation."""
        self.token_for("alice", "alicepass123")
        self.exhaust_daily("alice")

        body = self.client.get("/api/quota", params={"session_id": "alice"}).json()
        self.assertEqual(body["personal"]["user_id"], "guest_alice")
        self.assertEqual(body["personal"]["daily_used"], 0)

    def test_personal_and_global_caps_are_reported_separately(self):
        token = self.token_for("alice", "alicepass123")
        self.exhaust_daily("alice")

        body = self.client.get("/api/quota", headers=self.auth(token)).json()
        self.assertTrue(body["personal"]["exhausted"])
        # The user's own cap being spent says nothing about service capacity.
        self.assertFalse(body["global"]["exhausted"])

    def test_global_cap_exhaustion_is_reported_independently(self):
        token = self.token_for("alice", "alicepass123")
        self.exhaust_global()

        body = self.client.get("/api/quota", headers=self.auth(token)).json()
        self.assertTrue(body["global"]["exhausted"])
        self.assertEqual(body["global"]["limit"], settings.global_daily_query_limit)
        # The service being full says nothing about this user's own untouched allocation.
        self.assertFalse(body["personal"]["exhausted"])

    def test_quota_does_not_consume_an_allocation(self):
        token = self.token_for("alice", "alicepass123")
        for _ in range(3):
            self.client.get("/api/quota", headers=self.auth(token))
        body = self.client.get("/api/quota", headers=self.auth(token)).json()
        self.assertEqual(body["personal"]["daily_used"], 0)


class TestResearchStream(ApiTestCase):
    """The SSE endpoint must stream the five pipeline steps, for users and guests alike."""

    def test_authenticated_stream_emits_five_steps_then_complete(self):
        token = self.token_for("alice", "alicepass123")
        resp, events = self.stream_research(
            params={"query": "what is quantum computing"}, headers=self.auth(token)
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.headers["content-type"].startswith("text/event-stream"))

        names = [e["event"] for e in events]
        self.assertEqual(names, ["accepted", "step", "step", "step", "step", "step", "complete"])

        steps = [e["data"]["step"] for e in events if e["event"] == "step"]
        self.assertEqual(steps, list(PIPELINE_STEPS))
        self.assertEqual(steps, ["planning", "searching", "summarizing", "fact_checking", "writing"])

        for idx, evt in enumerate([e for e in events if e["event"] == "step"], 1):
            self.assertEqual(evt["data"]["index"], idx)
            self.assertEqual(evt["data"]["status"], "completed")
            self.assertEqual(evt["data"]["total_steps"], 5)
            self.assertGreaterEqual(evt["data"]["elapsed_sec"], 0)

    def test_step_payloads_carry_progress_detail(self):
        token = self.token_for("alice", "alicepass123")
        _, events = self.stream_research(
            params={"query": "what is quantum computing"}, headers=self.auth(token)
        )
        by_step = {e["data"]["step"]: e["data"]["payload"] for e in events if e["event"] == "step"}

        self.assertEqual(by_step["planning"]["sub_queries"], ["sub query one", "sub query two"])
        self.assertEqual(by_step["searching"]["source_count"], 3)
        self.assertEqual(by_step["summarizing"]["claim_count"], 3)
        self.assertEqual(by_step["fact_checking"]["contradiction_count"], 0)
        self.assertGreater(by_step["writing"]["report_chars"], 0)

    def test_complete_event_payload_shape(self):
        token = self.token_for("alice", "alicepass123")
        _, events = self.stream_research(
            params={"query": "what is quantum computing"}, headers=self.auth(token)
        )
        data = events[-1]["data"]

        self.assertEqual(events[-1]["event"], "complete")
        self.assertIn("Findings with citation", data["report"])
        self.assertEqual(len(data["sources"]), 3)
        self.assertEqual(data["sources"][0]["index"], 1)
        self.assertEqual(data["sources"][0]["url"], "https://a.example.com/a")
        self.assertTrue(data["sources"][0]["excerpt"])
        self.assertTrue(data["saved_to_history"])
        self.assertTrue(data["session_id"])
        self.assertFalse(data["is_fallback"])
        self.assertGreater(data["telemetry"]["usage"]["total_tokens"], 0)
        # The UI reports time and tokens, never the underlying model's brand name.
        self.assertNotIn("model", data["telemetry"]["usage"])

    def test_guest_stream_works_and_is_not_persisted(self):
        resp, events = self.stream_research(
            params={"query": "guest question", "session_id": "guest_web_xyz"}
        )

        self.assertEqual(resp.status_code, 200)
        steps = [e["data"]["step"] for e in events if e["event"] == "step"]
        self.assertEqual(steps, list(PIPELINE_STEPS))

        data = events[-1]["data"]
        self.assertFalse(data["saved_to_history"])
        self.assertIsNone(data["session_id"])

        accepted = events[0]["data"]
        self.assertFalse(accepted["authenticated"])
        self.assertFalse(accepted["persisted"])

    def test_guest_stream_still_consumes_its_own_scoped_quota(self):
        self.stream_research(params={"query": "guest question", "session_id": "guest_web_xyz"})
        body = self.client.get("/api/quota", params={"session_id": "guest_web_xyz"}).json()
        self.assertEqual(body["personal"]["daily_used"], 1)

    def test_invalid_query_returns_400_before_stream_opens(self):
        token = self.token_for("alice", "alicepass123")
        resp = self.client.get("/api/research/stream", params={"query": "   "}, headers=self.auth(token))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "invalid_request")

    def test_oversized_query_returns_400_without_consuming_quota(self):
        token = self.token_for("alice", "alicepass123")
        resp = self.client.get(
            "/api/research/stream",
            params={"query": "A" * (settings.max_query_length + 1)},
            headers=self.auth(token),
        )
        self.assertEqual(resp.status_code, 400)
        quota = self.client.get("/api/quota", headers=self.auth(token)).json()
        self.assertEqual(quota["personal"]["daily_used"], 0)


class TestResearchStreamContradictions(ApiTestCase):
    """Contradiction detail must reach the client so the amber callout can render."""

    contradictions = True

    def test_contradictions_are_streamed_when_present(self):
        token = self.token_for("alice", "alicepass123")
        _, events = self.stream_research(params={"query": "contested topic"}, headers=self.auth(token))

        fact_step = next(
            e for e in events if e["event"] == "step" and e["data"]["step"] == "fact_checking"
        )
        self.assertEqual(fact_step["data"]["payload"]["contradiction_count"], 1)
        self.assertEqual(len(events[-1]["data"]["fact_check"]["contradictions"]), 1)


class TestRateLimitResponses(ApiTestCase):
    """Both rate-limit types must surface with the right status and discriminator."""

    def test_personal_daily_cap_returns_429_scoped_personal(self):
        token = self.token_for("alice", "alicepass123")
        self.exhaust_daily("alice")

        resp = self.client.get("/api/research/stream", params={"query": "anything"}, headers=self.auth(token))
        self.assertEqual(resp.status_code, 429)
        body = resp.json()
        self.assertEqual(body["error"], "daily_limit_exceeded")
        self.assertEqual(body["cap_scope"], "personal")
        self.assertGreater(body["retry_after_seconds"], 0)
        self.assertIn("Daily research quota reached", body["message"])

    def test_global_daily_cap_returns_429_scoped_global(self):
        token = self.token_for("alice", "alicepass123")
        self.exhaust_global()

        resp = self.client.get("/api/research/stream", params={"query": "anything"}, headers=self.auth(token))
        self.assertEqual(resp.status_code, 429)
        body = resp.json()
        self.assertEqual(body["error"], "daily_limit_exceeded")
        self.assertEqual(body["cap_scope"], "global")
        self.assertIn("Service-wide shared research capacity reached", body["message"])

    def test_personal_and_global_cap_messages_are_distinct(self):
        """The two caps mean different things and must never share copy."""
        token = self.token_for("alice", "alicepass123")
        self.exhaust_daily("alice")
        personal = self.client.get(
            "/api/research/stream", params={"query": "q"}, headers=self.auth(token)
        ).json()

        self.setUp()
        token = self.token_for("bob", "bobpass12345")
        self.exhaust_global()
        service_wide = self.client.get(
            "/api/research/stream", params={"query": "q"}, headers=self.auth(token)
        ).json()

        self.assertNotEqual(personal["message"], service_wide["message"])
        self.assertEqual(personal["cap_scope"], "personal")
        self.assertEqual(service_wide["cap_scope"], "global")

    def test_burst_rpm_limit_returns_429_with_short_retry(self):
        token = self.token_for("alice", "alicepass123")
        now_ts = datetime.now(timezone.utc).timestamp()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.storage.save_rate_limit_record("alice", {
            "user_id": "alice",
            "daily_date": today,
            "daily_count": 1,
            "minute_timestamps": [now_ts] * settings.requests_per_minute_limit,
        })

        resp = self.client.get("/api/research/stream", params={"query": "anything"}, headers=self.auth(token))
        self.assertEqual(resp.status_code, 429)
        body = resp.json()
        self.assertEqual(body["error"], "burst_rate_limit_exceeded")
        self.assertGreater(body["retry_after_seconds"], 0)
        self.assertLessEqual(body["retry_after_seconds"], 60)
        self.assertIn("Requests-per-minute limit reached", body["message"])
        # A burst limit is not a daily cap and must not be labelled as one.
        self.assertIsNone(body.get("cap_scope"))

    def test_guest_daily_cap_returns_429_scoped_personal(self):
        self.exhaust_daily("guest_web_limited")
        resp = self.client.get(
            "/api/research/stream",
            params={"query": "anything", "session_id": "guest_web_limited"},
        )
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.json()["cap_scope"], "personal")


class TestHistoryRoutes(ApiTestCase):
    """History endpoints delegate isolation to the dual-key storage filter."""

    def test_history_requires_authentication(self):
        self.assertEqual(self.client.get("/api/history").status_code, 401)
        self.assertEqual(self.client.get("/api/history/some-session").status_code, 401)
        self.assertEqual(self.client.delete("/api/history/some-session").status_code, 401)

    def test_completed_research_appears_in_history(self):
        token = self.token_for("alice", "alicepass123")
        session_id = self.run_research(token, "what is quantum computing")

        body = self.client.get("/api/history", headers=self.auth(token)).json()
        self.assertEqual(body["total"], 1)
        item = body["sessions"][0]
        self.assertEqual(item["session_id"], session_id)
        self.assertEqual(item["query"], "what is quantum computing")
        self.assertEqual(item["source_count"], 3)
        self.assertFalse(item["is_fallback"])

    def test_get_saved_session_detail(self):
        token = self.token_for("alice", "alicepass123")
        session_id = self.run_research(token, "what is quantum computing")

        detail = self.client.get(f"/api/history/{session_id}", headers=self.auth(token)).json()
        self.assertEqual(detail["user_id"], "alice")
        self.assertEqual(detail["plan"], ["sub query one", "sub query two"])
        self.assertIn("Findings with citation", detail["report"])
        self.assertEqual(len(detail["sources"]), 3)

    def test_delete_session(self):
        token = self.token_for("alice", "alicepass123")
        session_id = self.run_research(token, "disposable question")

        resp = self.client.delete(f"/api/history/{session_id}", headers=self.auth(token))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["deleted"])
        self.assertEqual(self.client.get("/api/history", headers=self.auth(token)).json()["total"], 0)

        repeat = self.client.delete(f"/api/history/{session_id}", headers=self.auth(token))
        self.assertEqual(repeat.status_code, 404)

    def test_guest_research_is_not_written_to_any_history(self):
        self.stream_research(params={"query": "guest question", "session_id": "guest_web_1"})
        self.assertEqual(self.storage.sessions_col.count_documents({}), 0)


class TestCrossUserIsolation(ApiTestCase):
    """Phase 7 acceptance criterion: two accounts must not see each other's research."""

    def setUp(self):
        super().setUp()
        self.alice_token = self.token_for("alice", "alicepass123", "alice@example.com")
        self.bob_token = self.token_for("bob", "bobpass123456", "bob@example.com")
        self.alice_session = self.run_research(self.alice_token, "alice private research question")
        self.bob_session = self.run_research(self.bob_token, "bob private research question")

    def test_each_user_sees_only_their_own_history_list(self):
        alice = self.client.get("/api/history", headers=self.auth(self.alice_token)).json()
        bob = self.client.get("/api/history", headers=self.auth(self.bob_token)).json()

        self.assertEqual([s["query"] for s in alice["sessions"]], ["alice private research question"])
        self.assertEqual([s["query"] for s in bob["sessions"]], ["bob private research question"])
        self.assertEqual(alice["total"], 1)
        self.assertEqual(bob["total"], 1)

    def test_user_cannot_read_another_users_session_by_id(self):
        resp = self.client.get(f"/api/history/{self.alice_session}", headers=self.auth(self.bob_token))
        self.assertEqual(resp.status_code, 404)

        resp = self.client.get(f"/api/history/{self.bob_session}", headers=self.auth(self.alice_token))
        self.assertEqual(resp.status_code, 404)

    def test_user_cannot_delete_another_users_session(self):
        resp = self.client.delete(f"/api/history/{self.alice_session}", headers=self.auth(self.bob_token))
        self.assertEqual(resp.status_code, 404)

        # Alice's session survives Bob's attempt.
        still_there = self.client.get(f"/api/history/{self.alice_session}", headers=self.auth(self.alice_token))
        self.assertEqual(still_there.status_code, 200)

    def test_quota_is_tracked_per_user(self):
        alice = self.client.get("/api/quota", headers=self.auth(self.alice_token)).json()
        bob = self.client.get("/api/quota", headers=self.auth(self.bob_token)).json()
        self.assertEqual(alice["personal"]["daily_used"], 1)
        self.assertEqual(bob["personal"]["daily_used"], 1)
        self.assertEqual(alice["personal"]["user_id"], "alice")
        self.assertEqual(bob["personal"]["user_id"], "bob")


class TestSpaServing(ApiTestCase):
    """When a frontend build is present, SPA routes must not be shadowed by API routes.

    /history is both a client-side route of the app and an API path. If the API were also
    mounted unprefixed, loading or refreshing /history in a browser would return JSON
    instead of the app, so the API is confined to /api.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        dist = Path(self.tmp.name) / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<!doctype html><title>SPA</title>", encoding="utf-8")
        (dist / "assets" / "app.js").write_text("// built bundle", encoding="utf-8")

        self.storage = ResearchStorage(force_mock=True, db_name=f"test_api_{self.id()}")
        self.pipeline = build_mock_pipeline(self.storage)
        deps.reset_state(storage=self.storage, pipeline=self.pipeline)
        with patch.object(settings, "frontend_dist_dir", str(dist)):
            self.app = create_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def tearDown(self):
        super().tearDown()
        self.tmp.cleanup()

    def test_spa_routes_serve_the_app_not_json(self):
        for route in ["/", "/history", "/history/some-session-id", "/login", "/research"]:
            resp = self.client.get(route)
            self.assertEqual(resp.status_code, 200, route)
            self.assertIn("text/html", resp.headers["content-type"], route)
            self.assertIn("SPA", resp.text, route)

    def test_api_routes_still_resolve_under_the_api_prefix(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        # Still a real 401, not the SPA fallback.
        resp = self.client.get("/api/history")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("application/json", resp.headers["content-type"])

    def test_unknown_api_paths_404_instead_of_returning_html(self):
        resp = self.client.get("/api/does-not-exist")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("application/json", resp.headers["content-type"])

    def test_built_assets_are_served(self):
        resp = self.client.get("/assets/app.js")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("built bundle", resp.text)


if __name__ == "__main__":
    unittest.main()
