import sys
import getpass
import argparse
from typing import Optional
from colorama import init, Fore, Style

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import logging
from src.logger import setup_logging
from src.config import settings, BASE_DIR
from src.pipeline import ResearchPipeline
from src.auth import (
    register_user,
    authenticate_user,
    verify_access_token,
    AuthError,
    UserIdentity,
)
from src.storage import ResearchStorage
from src.rate_limiter import (
    RateLimiter,
    RateLimitExceededError,
    DailyLimitExceededError,
    BurstRateLimitExceededError,
    AccountLockedError,
)

init(autoreset=True)


def print_banner():
    print(Fore.CYAN + Style.BRIGHT + "=" * 75)
    print(Fore.CYAN + Style.BRIGHT + "   [*] Multi-Agent Research Assistant — Phase 6 (Rate Limiting & Quotas)")
    print(Fore.CYAN + Style.BRIGHT + "   ⏱️ Rate Limiter ➔ 🔐 Auth ➔ 🧠 Plan ➔ 🔍 Search ➔ 📝 Summarize ➔ ✍️ Report")
    print(Fore.CYAN + Style.BRIGHT + "=" * 75 + "\n")


def handle_register(storage: ResearchStorage, user_arg: Optional[str], password_arg: Optional[str], email_arg: Optional[str]):
    """Handle new user registration."""
    username = user_arg or input(Fore.YELLOW + "Enter desired username: " + Fore.WHITE).strip()
    if not username:
        print(Fore.RED + "❌ Username cannot be empty.")
        return

    password = password_arg or getpass.getpass(Fore.YELLOW + "Enter password (min 8 chars): " + Fore.WHITE)
    if not password:
        print(Fore.RED + "❌ Password cannot be empty.")
        return

    try:
        register_user(storage, user_id=username, password=password, email=email_arg)
        _, token = authenticate_user(storage, user_id=username, password=password)
        print(Fore.GREEN + Style.BRIGHT + f"\n✅ User '{username}' registered successfully!")
        print(Fore.GREEN + f"🔑 Your signed JWT access token:\n")
        print(Fore.YELLOW + token + "\n")
        print(Fore.LIGHTBLACK_EX + "💡 Use this token in future requests with: --token <TOKEN>\n")
    except AuthError as e:
        print(Fore.RED + Style.BRIGHT + f"\n❌ Registration Failed: {e}\n")


def handle_login(storage: ResearchStorage, user_arg: Optional[str], password_arg: Optional[str]) -> Optional[UserIdentity]:
    """Handle user authentication via credentials with lockout protection."""
    username = user_arg or input(Fore.YELLOW + "Enter username: " + Fore.WHITE).strip()
    if not username:
        print(Fore.RED + "❌ Username cannot be empty.")
        return None

    password = password_arg or getpass.getpass(Fore.YELLOW + "Enter password: " + Fore.WHITE)
    if not password:
        print(Fore.RED + "❌ Password cannot be empty.")
        return None

    try:
        user_doc, token = authenticate_user(storage, user_id=username, password=password)
        identity = verify_access_token(token)
        print(Fore.GREEN + Style.BRIGHT + f"\n✅ Logged in successfully as '{identity.user_id}'!")
        print(Fore.GREEN + f"🔑 Access Token:\n" + Fore.YELLOW + f"{token}\n")
        return identity
    except AccountLockedError as e:
        print(Fore.RED + Style.BRIGHT + f"\n🔒 Account Locked: {e}\n")
        return None
    except AuthError as e:
        print(Fore.RED + Style.BRIGHT + f"\n❌ Authentication Failed: {e}\n")
        return None


def handle_session_history(storage: ResearchStorage, user_id: str):
    """Display session history for an authenticated user."""
    print(Fore.YELLOW + f"📂 Research Sessions for User '{user_id}':\n")
    sessions = storage.list_user_sessions(user_id=user_id)
    if not sessions:
        print(Fore.LIGHTBLACK_EX + "   (No saved research sessions found)\n")
        return

    for idx, s in enumerate(sessions, 1):
        dt_str = s.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        print(Fore.CYAN + f"   [{idx}] Session ID: {Fore.WHITE}{s.session_id}")
        print(Fore.YELLOW + f"       Query:      {Fore.WHITE}{s.query}")
        print(Fore.LIGHTBLACK_EX + f"       Created At: {dt_str} | Sources: {len(s.sources)}")
        print()


def handle_load_session(storage: ResearchStorage, user_id: str, session_id: str):
    """Retrieve and display a specific saved session for an authenticated user."""
    session = storage.get_session(user_id=user_id, session_id=session_id)
    if not session:
        print(Fore.RED + f"❌ Session '{session_id}' not found for user '{user_id}' (Dual-key isolation enforced).")
        return

    print(Fore.CYAN + Style.BRIGHT + "=" * 75)
    print(Fore.CYAN + Style.BRIGHT + f"   📄 SAVED REPORT: {session.query}")
    print(Fore.LIGHTBLACK_EX + f"   Session: {session.session_id} | User: {session.user_id} | {session.created_at}")
    print(Fore.CYAN + Style.BRIGHT + "=" * 75)
    print(Fore.WHITE + session.report)
    print(Fore.CYAN + Style.BRIGHT + "=" * 75 + "\n")


def handle_delete_session(storage: ResearchStorage, user_id: str, session_id: str):
    """Delete a saved session for an authenticated user."""
    deleted = storage.delete_session(user_id=user_id, session_id=session_id)
    if deleted:
        print(Fore.GREEN + f"✅ Successfully deleted session '{session_id}' for user '{user_id}'.")
    else:
        print(Fore.RED + f"❌ Session '{session_id}' not found or unauthorized for user '{user_id}'.")


def handle_quota_status(storage: ResearchStorage, user_id: str):
    """Display rate limit and quota status for a user."""
    limiter = RateLimiter(storage=storage)
    q = limiter.get_quota_status(user_id)
    hours = q.seconds_to_daily_reset // 3600
    mins = (q.seconds_to_daily_reset % 3600) // 60

    print(Fore.CYAN + Style.BRIGHT + "=" * 75)
    print(Fore.CYAN + Style.BRIGHT + f"   📊 USER QUOTA & RATE LIMIT TELEMETRY: {user_id}")
    print(Fore.CYAN + Style.BRIGHT + "=" * 75)
    print(Fore.YELLOW + f"  • Daily Query Cap:         {Fore.WHITE}{q.daily_used} / {q.daily_limit} used ({Fore.GREEN}{q.daily_remaining} remaining{Fore.WHITE})")
    print(Fore.YELLOW + f"  • Daily Reset Time:        {Fore.WHITE}00:00 UTC (in {hours}h {mins}m)")
    print(Fore.YELLOW + f"  • Burst Rate (RPM):        {Fore.WHITE}{q.rpm_used} / {q.rpm_limit} req/min ({Fore.GREEN}{q.rpm_remaining} slots available{Fore.WHITE})")
    print(Fore.CYAN + Style.BRIGHT + "=" * 75 + "\n")


import uuid


def run_pipeline(
    query: str,
    user_id: Optional[str] = None,
    guest_id: Optional[str] = None,
    storage: Optional[ResearchStorage] = None,
):
    effective_user = user_id or guest_id or "guest"
    print(Fore.YELLOW + f"📌 Research Question: " + Fore.WHITE + f"{query}")
    if user_id:
        print(Fore.GREEN + f"👤 Authenticated User: {user_id}\n")
    else:
        print(Fore.LIGHTBLACK_EX + f"👤 Guest Mode ({effective_user} — Session not saved to persistent account)\n")

    try:
        pipeline = ResearchPipeline(storage=storage)

        # Step 1: Planning
        print(Fore.BLUE + "🧠 [Step 1/5] Planner Agent analyzing query and planning strategy...")
        result = pipeline.run(query=query, user_id=user_id, session_id=guest_id if not user_id else None)

        if result.is_fallback:
            print(Fore.YELLOW + Style.BRIGHT + f"   ⚠️ Fallback activated: {result.plan_rationale}\n")
        else:
            print(Fore.GREEN + f"✅ Planner generated {len(result.sub_queries)} sub-queries in {result.planning_time_sec}s:")
            for idx, sq in enumerate(result.sub_queries, 1):
                print(Fore.CYAN + f"   [{idx}] " + Fore.WHITE + f"{sq}")
            if result.plan_rationale:
                print(Fore.LIGHTBLACK_EX + f"   Rationale: {result.plan_rationale}\n")
            else:
                print()

        # Step 2: Search
        print(Fore.BLUE + f"🔍 [Step 2/5] Search Agent executed multi-search with URL deduplication:")
        print(Fore.GREEN + f"✅ Retrieved {len(result.search_results)} unique sources in {result.search_time_sec}s\n")

        # Step 3: Summarize
        print(Fore.MAGENTA + f"📝 [Step 3/5] Summarizer Agent distilled claims & eliminated noise:")
        if result.summary_output and result.summary_output.sources:
            total_claims = sum(len(s.key_claims) for s in result.summary_output.sources)
            print(Fore.GREEN + f"✅ Extracted {total_claims} factual claims across {len(result.summary_output.sources)} sources in {result.summarization_time_sec}s\n")
        else:
            print(Fore.YELLOW + f"ℹ️ Summarization completed in {result.summarization_time_sec}s\n")

        # Step 4: Fact-Check
        print(Fore.CYAN + f"🔬 [Step 4/5] Fact-Checker Agent cross-referenced claims across sources:")
        if result.fact_check_output:
            fc = result.fact_check_output
            print(Fore.GREEN + f"✅ Verified in {result.fact_check_time_sec}s: {len(fc.consensus_facts)} Consensus Facts | {len(fc.unique_facts)} Unique Findings")
            if fc.contradictions:
                print(Fore.YELLOW + Style.BRIGHT + f"   ⚠️ Flagged {len(fc.contradictions)} Contradiction(s)/Discrepancies:")
                for c in fc.contradictions:
                    print(Fore.YELLOW + f"     • [{c.topic}]: {c.conflict}")
            print()
        else:
            print(Fore.YELLOW + f"ℹ️ Fact-checking completed in {result.fact_check_time_sec}s\n")

        # Step 5: Synthesis
        print(Fore.MAGENTA + "✍️ [Step 5/5] Writer Agent synthesized final verified report:")
        print(Fore.GREEN + f"✅ Synthesis completed in {result.synthesis_time_sec}s\n")

        print(Fore.CYAN + Style.BRIGHT + "-" * 75)
        print(Fore.CYAN + Style.BRIGHT + "                     📄 FINAL RESEARCH REPORT")
        print(Fore.CYAN + Style.BRIGHT + "-" * 75)
        print(Fore.WHITE + result.report)
        print(Fore.CYAN + Style.BRIGHT + "-" * 75)

        # Performance and Telemetry Box
        print(Fore.YELLOW + "\n📊 Granular Pipeline Telemetry:")
        if result.session_id:
            print(Fore.WHITE + f"  • Session ID:              {result.session_id}")
            print(Fore.WHITE + f"  • User ID:                 {result.user_id}")
        else:
            print(Fore.LIGHTBLACK_EX + f"  • Session Storage:         Skipped (Guest/Unauthenticated)")

        if result.quota_status:
            qs = result.quota_status
            print(Fore.GREEN + f"  • Daily Quota:             {qs.daily_used} / {qs.daily_limit} used ({qs.daily_remaining} left)")
            print(Fore.GREEN + f"  • Burst Rate:              {qs.rpm_used} / {qs.rpm_limit} req/min")

        print(Fore.WHITE + f"  • Step 1 (Planning):       {result.planning_time_sec}s")
        print(Fore.WHITE + f"  • Step 2 (Multi-Search):   {result.search_time_sec}s")
        print(Fore.WHITE + f"  • Step 3 (Summarization):  {result.summarization_time_sec}s")
        print(Fore.WHITE + f"  • Step 4 (Fact-Checking):  {result.fact_check_time_sec}s")
        print(Fore.WHITE + f"  • Step 5 (Synthesis):      {result.synthesis_time_sec}s")
        print(Fore.GREEN + Style.BRIGHT + f"  • Total Execution Time:    {result.total_time_sec}s (Target: <30s)")
        if result.usage:
            print(Fore.WHITE + f"  • Model:                   {result.usage.get('model', 'N/A')}")
            print(Fore.WHITE + f"  • Planner Tokens:          {result.usage.get('planner_tokens', 0)}")
            print(Fore.WHITE + f"  • Summarizer Tokens:       {result.usage.get('summarizer_tokens', 0)}")
            print(Fore.WHITE + f"  • Fact-Checker Tokens:     {result.usage.get('fact_checker_tokens', 0)}")
            print(Fore.WHITE + f"  • Writer Tokens:           {result.usage.get('writer_tokens', 0)}")
            print(Fore.GREEN + Style.BRIGHT + f"  • Total Tokens Consumed:   {result.usage.get('total_tokens', 0)}")
        print(Fore.CYAN + "=" * 75 + "\n")

    except BurstRateLimitExceededError as e:
        print(Fore.RED + Style.BRIGHT + f"\n⏱️ Rate Limit Exceeded (RPM): {e}")
        print(Fore.YELLOW + f"💡 Please wait {e.retry_after_seconds}s before submitting another research query.\n")
    except DailyLimitExceededError as e:
        print(Fore.RED + Style.BRIGHT + f"\n🛑 Daily Quota Reached: {e}")
        print(Fore.YELLOW + "💡 Your daily search quota will reset automatically at 00:00 UTC.\n")
    except ValueError as e:
        print(Fore.RED + Style.BRIGHT + f"\n❌ Configuration Error: {e}")
        print(Fore.YELLOW + f"💡 Please ensure you have created a valid .env file in:\n   {BASE_DIR / '.env'}")
    except Exception as e:
        print(Fore.RED + Style.BRIGHT + f"\n❌ Execution Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Research Assistant (Phase 6 CLI - Rate Limiting & Quotas)")
    parser.add_argument("-q", "--query", type=str, help="Research question to process")
    parser.add_argument("-u", "--user", type=str, default=None, help="Username (for register or login)")
    parser.add_argument("-p", "--password", type=str, default=None, help="Password (for register or login)")
    parser.add_argument("--email", type=str, default=None, help="Optional email for registration")
    parser.add_argument("--register", action="store_true", help="Register a new user account")
    parser.add_argument("--login", action="store_true", help="Authenticate with credentials and obtain a JWT token")
    parser.add_argument("--token", type=str, default=None, help="Signed JWT access token for authentication")
    parser.add_argument("--quota", action="store_true", help="View current rate limit and daily quota usage")
    parser.add_argument("--history", action="store_true", help="List past research session history (Authentication Required)")
    parser.add_argument("--load-session", type=str, metavar="SESSION_ID", help="Load and view a past session report (Authentication Required)")
    parser.add_argument("--delete-session", type=str, metavar="SESSION_ID", help="Delete a past research session (Authentication Required)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(level=log_level)

    print_banner()
    storage = ResearchStorage()

    # Flow 1: Register
    if args.register:
        handle_register(storage, user_arg=args.user, password_arg=args.password, email_arg=args.email)
        return

    # Flow 2: Authenticate Identity
    authenticated_identity: Optional[UserIdentity] = None

    if args.token:
        try:
            authenticated_identity = verify_access_token(args.token)
            print(Fore.GREEN + f"🔑 Authenticated via JWT token as user: {authenticated_identity.user_id}\n")
        except AuthError as e:
            print(Fore.RED + Style.BRIGHT + f"❌ Authentication Error: {e}")
            sys.exit(1)
    elif args.login:
        authenticated_identity = handle_login(storage, user_arg=args.user, password_arg=args.password)
        if not authenticated_identity:
            sys.exit(1)

    effective_user = authenticated_identity.user_id if authenticated_identity else "guest"

    # Flow 3: Quota Inspection
    if args.quota:
        handle_quota_status(storage, effective_user)
        return

    # Flow 4: Protected Session Actions (Strictly require authenticated identity)
    if args.history:
        if not authenticated_identity:
            print(Fore.RED + Style.BRIGHT + "❌ Authentication Required: Viewing session history requires authentication.\n"
                  "Please use --login or pass a valid --token <JWT>.")
            sys.exit(1)
        handle_session_history(storage, authenticated_identity.user_id)
        return

    if args.load_session:
        if not authenticated_identity:
            print(Fore.RED + Style.BRIGHT + "❌ Authentication Required: Loading session reports requires authentication.\n"
                  "Please use --login or pass a valid --token <JWT>.")
            sys.exit(1)
        handle_load_session(storage, authenticated_identity.user_id, args.load_session)
        return

    if args.delete_session:
        if not authenticated_identity:
            print(Fore.RED + Style.BRIGHT + "❌ Authentication Required: Deleting sessions requires authentication.\n"
                  "Please use --login or pass a valid --token <JWT>.")
            sys.exit(1)
        handle_delete_session(storage, authenticated_identity.user_id, args.delete_session)
        return

    # Flow 5: Execute Research Pipeline
    user_id = authenticated_identity.user_id if authenticated_identity else None
    cli_guest_id = None if user_id else f"guest_cli_{uuid.uuid4().hex[:8]}"

    if args.query:
        run_pipeline(args.query, user_id=user_id, guest_id=cli_guest_id, storage=storage)
    else:
        try:
            while True:
                user_input = input(Fore.GREEN + Style.BRIGHT + "Enter research question (or 'q' to quit): " + Fore.WHITE)
                if not user_input or user_input.strip().lower() in ['q', 'exit', 'quit']:
                    print(Fore.CYAN + "\nExiting. Happy researching! 👋")
                    break
                print()
                run_pipeline(user_input.strip(), user_id=user_id, guest_id=cli_guest_id, storage=storage)
        except KeyboardInterrupt:
            print(Fore.CYAN + "\n\nExiting. Happy researching! 👋")
            sys.exit(0)


if __name__ == "__main__":
    main()
