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
from src.logger import setup_logging
from src.config import settings, BASE_DIR
from src.pipeline import ResearchPipeline

init(autoreset=True)


def print_banner():
    print(Fore.CYAN + Style.BRIGHT + "=" * 70)
    print(Fore.CYAN + Style.BRIGHT + "   [*] Multi-Agent Research Assistant — Phase 2 (Planner + Multi-Search)")
    print(Fore.CYAN + Style.BRIGHT + "   🧠 Planner  -->  🔍 Search (Deduplicated)  -->  ✍️ Writer")
    print(Fore.CYAN + Style.BRIGHT + "=" * 70 + "\n")


def run_pipeline(query: str):
    print(Fore.YELLOW + f"📌 Research Question: " + Fore.WHITE + f"{query}\n")
    print(Fore.BLUE + "🧠 [Step 1/3] Planner Agent analyzing query and decomposing into sub-questions...")

    try:
        pipeline = ResearchPipeline()
        result = pipeline.run(query=query)

        # Display Planner breakdown
        if result.is_fallback:
            print(Fore.YELLOW + Style.BRIGHT + f"⚠️ [WARNING] Planner fallback was triggered (single query search):\n   Reason: {result.plan_rationale}\n")
        else:
            print(Fore.GREEN + f"✅ Planner generated {len(result.sub_queries)} sub-queries in {result.planning_time_sec}s:")
            for idx, sq in enumerate(result.sub_queries, 1):
                print(Fore.CYAN + f"   [{idx}] " + Fore.WHITE + f"{sq}")
            if result.plan_rationale:
                print(Fore.LIGHTBLACK_EX + f"   Rationale: {result.plan_rationale}\n")
            else:
                print()

        print(Fore.BLUE + f"🔍 [Step 2/3] Search Agent executing multi-search with URL deduplication...")
        print(Fore.GREEN + f"✅ Retrieved {len(result.search_results)} unique sources across all sub-queries in {result.search_time_sec}s\n")

        print(Fore.MAGENTA + "✍️ [Step 3/3] Writer Agent synthesizing multi-angle context via Groq...")
        print(Fore.GREEN + f"✅ Synthesis completed in {result.synthesis_time_sec}s\n")

        print(Fore.CYAN + Style.BRIGHT + "-" * 70)
        print(Fore.CYAN + Style.BRIGHT + "                     📄 RESEARCH REPORT")
        print(Fore.CYAN + Style.BRIGHT + "-" * 70)
        print(Fore.WHITE + result.report)
        print(Fore.CYAN + Style.BRIGHT + "-" * 70)

        # Performance and Telemetry Box
        print(Fore.YELLOW + "\n📊 Performance & Telemetry:")
        print(Fore.WHITE + f"  • Planning Latency:  {result.planning_time_sec}s")
        print(Fore.WHITE + f"  • Search Latency:    {result.search_time_sec}s")
        print(Fore.WHITE + f"  • Synthesis Latency: {result.synthesis_time_sec}s")
        print(Fore.GREEN + Style.BRIGHT + f"  • Total Time:        {result.total_time_sec}s (Target: <30s)")
        if result.usage:
            print(Fore.WHITE + f"  • Model Used:        {result.usage.get('model', 'N/A')}")
            print(Fore.WHITE + f"  • Planner Tokens:    {result.usage.get('planner_prompt_tokens', 0) + result.usage.get('planner_completion_tokens', 0)}")
            print(Fore.WHITE + f"  • Writer Tokens:     {result.usage.get('writer_prompt_tokens', 0) + result.usage.get('writer_completion_tokens', 0)}")
            print(Fore.WHITE + f"  • Total Tokens:      {result.usage.get('total_tokens', 0)}")
        print(Fore.CYAN + "=" * 70 + "\n")

    except ValueError as e:
        print(Fore.RED + Style.BRIGHT + f"\n❌ Configuration Error: {e}")
        print(Fore.YELLOW + f"💡 Please ensure you have created a valid .env file in:\n   {BASE_DIR / '.env'}")
    except Exception as e:
        print(Fore.RED + Style.BRIGHT + f"\n❌ Execution Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Research Assistant (Phase 2 CLI)")
    parser.add_argument("-q", "--query", type=str, help="Research question to process")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(level=log_level)

    print_banner()

    if args.query:
        run_pipeline(args.query)
    else:
        try:
            while True:
                user_input = input(Fore.GREEN + Style.BRIGHT + "Enter research question (or 'q' to quit): " + Fore.WHITE)
                if not user_input or user_input.strip().lower() in ['q', 'exit', 'quit']:
                    print(Fore.CYAN + "\nExiting. Happy researching! 👋")
                    break
                print()
                run_pipeline(user_input.strip())
        except KeyboardInterrupt:
            print(Fore.CYAN + "\n\nExiting. Happy researching! 👋")
            sys.exit(0)


if __name__ == "__main__":
    main()
