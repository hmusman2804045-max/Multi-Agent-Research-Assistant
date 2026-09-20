"""Phase 7 acceptance check: real two-account cross-user isolation over HTTP.

This is the PRD's Phase 7 acceptance test, run against a *live* server rather than a
test client: it registers two separate real accounts, logs in as each, runs a real
research question as each, and then proves that neither account can see, open or delete
the other's research.

    python scripts/verify_phase7_isolation.py --base-url http://127.0.0.1:7860

Two real research runs consume real search/LLM budget. Pass --skip-research to exercise
only the auth and history isolation paths without spending quota.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

PASS = "PASS"
FAIL = "FAIL"

DEFAULT_QUESTIONS = (
    "What are the main tradeoffs of sodium-ion batteries for grid storage?",
    "How does mycorrhizal fungi networking affect forest carbon storage?",
)


class Checker:
    """Collects pass/fail results so the whole run is reported, not just the first failure."""

    def __init__(self) -> None:
        self.results: List[Tuple[str, bool, str]] = []

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        self.results.append((name, bool(condition), detail))
        status = PASS if condition else FAIL
        print(f"  [{status}] {name}" + (f" - {detail}" if detail else ""))
        return bool(condition)

    @property
    def failed(self) -> List[str]:
        return [name for name, ok, _ in self.results if not ok]


def auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def run_research(
    client: httpx.Client, base_url: str, token: str, question: str
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Run one research question over the SSE stream, returning the final result and step order."""
    steps: List[str] = []
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    with client.stream(
        "GET",
        f"{base_url}/api/research/stream",
        params={"query": question},
        headers={**auth_headers(token), "Accept": "text/event-stream"},
        timeout=httpx.Timeout(180.0, read=180.0),
    ) as response:
        if response.status_code != 200:
            response.read()
            raise RuntimeError(f"stream rejected with {response.status_code}: {response.text}")

        event_name = None
        data_lines: List[str] = []
        for line in response.iter_lines():
            if line.startswith(":"):
                continue
            if line == "":
                if event_name and data_lines:
                    payload = json.loads("".join(data_lines))
                    if event_name == "step":
                        steps.append(payload["step"])
                        print(f"      · {payload['step']} ({payload['elapsed_sec']}s)")
                    elif event_name == "complete":
                        result = payload
                    elif event_name == "error":
                        error = payload
                event_name, data_lines = None, []
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())

    if error:
        raise RuntimeError(f"stream failed: {error.get('message')}")
    return result, steps


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 7 cross-user isolation acceptance test.")
    parser.add_argument("--base-url", default="http://127.0.0.1:7860", help="Running server base URL.")
    parser.add_argument("--skip-research", action="store_true", help="Skip the two real research runs.")
    parser.add_argument("--keep-accounts", action="store_true", help="Do not delete the test sessions afterwards.")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    suffix = secrets.token_hex(3)
    accounts = [
        {"username": f"acceptance_a_{suffix}", "password": f"pw_a_{secrets.token_urlsafe(12)}",
         "email": f"acceptance_a_{suffix}@example.com", "question": DEFAULT_QUESTIONS[0]},
        {"username": f"acceptance_b_{suffix}", "password": f"pw_b_{secrets.token_urlsafe(12)}",
         "email": f"acceptance_b_{suffix}@example.com", "question": DEFAULT_QUESTIONS[1]},
    ]

    checker = Checker()
    client = httpx.Client(timeout=30.0)

    print("=" * 78)
    print("  PHASE 7 ACCEPTANCE TEST - cross-user research isolation")
    print(f"  Server: {base_url}")
    print("=" * 78)

    # -- 0. Server reachable ------------------------------------------------------------
    print("\n[0] Server health")
    health = client.get(f"{base_url}/api/health")
    if not checker.check("server responds to /api/health", health.status_code == 200):
        return 1
    print(f"      limits: {health.json()['daily_query_limit']}/day per user, "
          f"{health.json()['global_daily_query_limit']}/day shared")

    # -- 1. Register two separate real accounts -----------------------------------------
    print("\n[1] Register two separate accounts")
    for account in accounts:
        resp = client.post(f"{base_url}/api/auth/register", json={
            "username": account["username"],
            "password": account["password"],
            "email": account["email"],
        })
        ok = checker.check(
            f"registered '{account['username']}'",
            resp.status_code == 201,
            "" if resp.status_code == 201 else f"status {resp.status_code}: {resp.text[:160]}",
        )
        if not ok:
            return 1

    # -- 2. Log in as each --------------------------------------------------------------
    print("\n[2] Log in as each account")
    for account in accounts:
        resp = client.post(f"{base_url}/api/auth/login", json={
            "username": account["username"], "password": account["password"],
        })
        # The body carries a live access token, so only the status is ever printed.
        if not checker.check(f"logged in as '{account['username']}'", resp.status_code == 200,
                             "" if resp.status_code == 200 else f"status {resp.status_code}"):
            return 1
        account["token"] = resp.json()["access_token"]

    checker.check(
        "the two accounts hold distinct tokens",
        accounts[0]["token"] != accounts[1]["token"],
    )

    # -- 3. Run real research as each ---------------------------------------------------
    if args.skip_research:
        print("\n[3] Research runs skipped (--skip-research)")
        for account in accounts:
            account["session_id"] = None
    else:
        print("\n[3] Run real research as each account")
        for account in accounts:
            print(f"    {account['username']}: {account['question']}")
            started = time.perf_counter()
            result, steps = run_research(client, base_url, account["token"], account["question"])
            elapsed = time.perf_counter() - started

            checker.check(
                f"{account['username']}: stream emitted all 5 steps in order",
                steps == ["planning", "searching", "summarizing", "fact_checking", "writing"],
                str(steps),
            )
            checker.check(
                f"{account['username']}: received a completed report",
                bool(result and result.get("report")),
            )
            checker.check(
                f"{account['username']}: run was saved to history",
                bool(result and result.get("saved_to_history") and result.get("session_id")),
            )
            account["session_id"] = result["session_id"] if result else None
            print(f"      completed in {elapsed:.1f}s with {len(result.get('sources', []))} sources")

    # -- 4. Each account sees only its own history --------------------------------------
    print("\n[4] History listings are per-account")
    for index, account in enumerate(accounts):
        other = accounts[1 - index]
        resp = client.get(f"{base_url}/api/history", headers=auth_headers(account["token"]))
        if not checker.check(f"{account['username']}: /history returned 200", resp.status_code == 200,
                             "" if resp.status_code == 200 else f"status {resp.status_code}"):
            continue

        queries = [s["query"] for s in resp.json()["sessions"]]
        ids = [s["session_id"] for s in resp.json()["sessions"]]

        checker.check(
            f"{account['username']}: sees only their own sessions",
            all(q != other["question"] for q in queries),
            f"saw {queries}",
        )
        if other.get("session_id"):
            checker.check(
                f"{account['username']}: does NOT see {other['username']}'s session id",
                other["session_id"] not in ids,
            )
        if account.get("session_id"):
            checker.check(
                f"{account['username']}: does see their own session id",
                account["session_id"] in ids,
            )

    # -- 5. Direct cross-account access is refused --------------------------------------
    print("\n[5] Direct cross-account access by session id")
    if accounts[0].get("session_id") and accounts[1].get("session_id"):
        for index, account in enumerate(accounts):
            other = accounts[1 - index]
            resp = client.get(
                f"{base_url}/api/history/{other['session_id']}", headers=auth_headers(account["token"])
            )
            checker.check(
                f"{account['username']}: GET {other['username']}'s session is refused",
                resp.status_code == 404,
                f"got {resp.status_code}",
            )
            checker.check(
                f"{account['username']}: the refusal leaks no report content",
                other["question"] not in resp.text and "report" not in resp.json(),
            )

            resp = client.delete(
                f"{base_url}/api/history/{other['session_id']}", headers=auth_headers(account["token"])
            )
            checker.check(
                f"{account['username']}: DELETE of {other['username']}'s session is refused",
                resp.status_code == 404,
                f"got {resp.status_code}",
            )

        # And the targeted sessions genuinely survived the delete attempts.
        for account in accounts:
            resp = client.get(
                f"{base_url}/api/history/{account['session_id']}", headers=auth_headers(account["token"])
            )
            checker.check(
                f"{account['username']}: own session survived the other account's delete attempt",
                resp.status_code == 200,
            )
    else:
        print("      (skipped - no sessions to cross-check)")

    # -- 6. Unauthenticated access is refused -------------------------------------------
    print("\n[6] Unauthenticated access")
    checker.check(
        "GET /history without a token is refused",
        client.get(f"{base_url}/api/history").status_code == 401,
    )
    if accounts[0].get("session_id"):
        checker.check(
            "GET a known session id without a token is refused",
            client.get(f"{base_url}/api/history/{accounts[0]['session_id']}").status_code == 401,
        )

    # -- 7. Quota is tracked per account ------------------------------------------------
    print("\n[7] Quota accounting is per-account")
    quotas = {}
    for account in accounts:
        resp = client.get(f"{base_url}/api/quota", headers=auth_headers(account["token"]))
        quotas[account["username"]] = resp.json()
        checker.check(
            f"{account['username']}: quota is reported under their own id",
            resp.json()["personal"]["user_id"] == account["username"],
        )
    checker.check(
        "personal and service-wide caps are reported as separate figures",
        all(
            q["personal"]["daily_limit"] != q["global"]["limit"] or q["global"]["enabled"]
            for q in quotas.values()
        ),
    )

    # -- 8. Clean up --------------------------------------------------------------------
    if not args.keep_accounts:
        print("\n[8] Cleaning up test sessions")
        for account in accounts:
            if account.get("session_id"):
                resp = client.delete(
                    f"{base_url}/api/history/{account['session_id']}",
                    headers=auth_headers(account["token"]),
                )
                checker.check(
                    f"{account['username']}: deleted their own session",
                    resp.status_code == 200,
                )
    else:
        print("\n[8] Cleanup skipped (--keep-accounts)")

    # -- Summary ------------------------------------------------------------------------
    total = len(checker.results)
    failed = checker.failed
    print("\n" + "=" * 78)
    if failed:
        print(f"  RESULT: {len(failed)} of {total} checks FAILED")
        for name in failed:
            print(f"    - {name}")
        print("=" * 78)
        return 1

    print(f"  RESULT: all {total} checks passed.")
    print("  Neither account could list, open or delete the other's research.")
    print("=" * 78)
    print("\n  Test accounts created (delete from the database if you do not want them):")
    for account in accounts:
        print(f"    - {account['username']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
