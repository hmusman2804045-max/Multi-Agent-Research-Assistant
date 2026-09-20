import sys
import argparse
from colorama import init, Fore, Style

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import logging
import logging
from src.logger import setup_logging
from src.config import settings, BASE_DIR
from src.pipeline import ResearchPipeline
from src.auth import create_access_token, verify_access_token, AuthError, UserIdentity
from src.storage import ResearchStorage

init(autoreset=True)


def print_banner():
    print(Fore.CYAN + Style.BRIGHT + "=" * 75)
    print(Fore.CYAN + Style.BRIGHT + "   [*] Multi-Agent Research Assistant — Phase 5 (Auth & User Isolation)")
    print(Fore.CYAN + Style.BRIGHT + "   🔐 Auth ➔ 🧠 Plan ➔ 🔍 Search ➔ 📝 Summarize ➔ 🔬 Fact-Check ➔ ✍️ Report")
    print(Fore.CYAN + Style.BRIGHT + "=" * 75 + "\n")


def resolve_user_identity(user_arg: str = None, token_arg: str = None) -> UserIdentity:
    """Resolve user identity from either token or explicit user ID."""
    if token_arg:
        identity = verify_access_token(token_arg)
        print(Fore.GREEN + f"🔑 Authenticated via JWT as user: {identity.user_id}\n")
        return identity
    elif user_arg:
        # Create an ephemeral or standard UserIdentity
        return UserIdentity(user_id=user_arg.strip(), expires_at=None)
    else:
        # Default anonymous user
        return UserIdentity(user_id="default_user", expires_at=None)


def handle_session_history(storage: ResearchStorage, user_id: str):
    """Display session history for a user."""
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
    """Retrieve and display a specific saved session."""
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
    """Delete a saved session."""
    deleted = storage.delete_session(user_id=user_id, session_id=session_id)
    if deleted:
        print(Fore.GREEN + f"✅ Successfully deleted session '{session_id}' for user '{user_id}'.")
    else:
        print(Fore.RED + f"❌ Session '{session_id}' not found or unauthorized for user '{user_id}'.")


def run_pipeline(query: str, user_id: str = "default_user", storage: ResearchStorage = None):
    print(Fore.YELLOW + f"📌 Research Question: " + Fore.WHITE + f"{query}")
    print(Fore.LIGHTBLACK_EX + f"👤 Authenticated User: {user_id}\n")

    try:
        pipeline = ResearchPipeline(storage=storage)

        # Step 1: Planning
        print(Fore.BLUE + "🧠 [Step 1/5] Planner Agent analyzing query and planning strategy...")
        result = pipeline.run(query=query, user_id=user_id)

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
        print(Fore.WHITE + f"  • Session ID:              {result.session_id}")
        print(Fore.WHITE + f"  • User ID:                 {result.user_id}")
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

    except ValueError as e:
        print(Fore.RED + Style.BRIGHT + f"\n❌ Configuration Error: {e}")
        print(Fore.YELLOW + f"💡 Please ensure you have created a valid .env file in:\n   {BASE_DIR / '.env'}")
    except Exception as e:
        print(Fore.RED + Style.BRIGHT + f"\n❌ Execution Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Research Assistant (Phase 5 CLI - Auth & User Isolation)")
    parser.add_argument("-q", "--query", type=str, help="Research question to process")
    parser.add_argument("-u", "--user", type=str, default=None, help="User identifier for isolated session storage")
    parser.add_argument("--token", type=str, default=None, help="Signed JWT access token for authentication")
    parser.add_argument("--generate-token", type=str, metavar="USER_ID", help="Generate a valid signed JWT for a given user ID")
    parser.add_argument("--history", action="store_true", help="List past research session history for the current user")
    parser.add_argument("--load-session", type=str, metavar="SESSION_ID", help="Load and view a past research session report")
    parser.add_argument("--delete-session", type=str, metavar="SESSION_ID", help="Delete a past research session")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(level=log_level)

    print_banner()

    # Handle token generation helper
    if args.generate_token:
        try:
            token = create_access_token(user_id=args.generate_token)
            print(Fore.GREEN + f"✅ Generated JWT Token for User '{args.generate_token}':\n")
            print(Fore.YELLOW + token + "\n")
            return
        except Exception as e:
            print(Fore.RED + f"❌ Failed to generate token: {e}")
            return

    # Resolve User Identity
    try:
        user_identity = resolve_user_identity(user_arg=args.user, token_arg=args.token)
    except AuthError as e:
        print(Fore.RED + Style.BRIGHT + f"❌ Authentication Error: {e}")
        sys.exit(1)

    storage = ResearchStorage()

    if args.history:
        handle_session_history(storage, user_identity.user_id)
        return

    if args.load_session:
        handle_load_session(storage, user_identity.user_id, args.load_session)
        return

    if args.delete_session:
        handle_delete_session(storage, user_identity.user_id, args.delete_session)
        return

    if args.query:
        run_pipeline(args.query, user_id=user_identity.user_id, storage=storage)
    else:
        try:
            while True:
                user_input = input(Fore.GREEN + Style.BRIGHT + "Enter research question (or 'q' to quit): " + Fore.WHITE)
                if not user_input or user_input.strip().lower() in ['q', 'exit', 'quit']:
                    print(Fore.CYAN + "\nExiting. Happy researching! 👋")
                    break
                print()
                run_pipeline(user_input.strip(), user_id=user_identity.user_id, storage=storage)
        except KeyboardInterrupt:
            print(Fore.CYAN + "\n\nExiting. Happy researching! 👋")
            sys.exit(0)


if __name__ == "__main__":
    main()
