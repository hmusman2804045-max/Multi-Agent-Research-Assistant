import time
import logging
from typing import Callable, List, Dict, Any, Optional
from pydantic import BaseModel, Field

from src.config import settings
from src.agents.planner_agent import PlannerAgent, PlanOutput
from src.agents.search_agent import SearchAgent
from src.agents.summarizer_agent import SummarizerAgent, SummaryOutput
from src.agents.fact_checker_agent import FactCheckerAgent, FactCheckOutput
from src.agents.writer_agent import WriterAgent
from src.security import sanitize_user_input

import uuid
from src.storage import ResearchStorage, ResearchSessionDocument
from src.rate_limiter import RateLimiter, QuotaStatus, RateLimitExceededError

logger = logging.getLogger(__name__)


# Canonical ordered identifiers for the five pipeline stages. External observers
# (e.g. the SSE streaming endpoint) rely on this exact ordering and naming.
PIPELINE_STEPS = ("planning", "searching", "summarizing", "fact_checking", "writing")

def resolve_rate_limit_identity(user_id: Optional[str], session_id: Optional[str]) -> str:
    """Resolve the identity key that rate limiting and quota accounting are scoped to.

    Authenticated users are scoped to their own user_id. Unauthenticated guests are scoped
    to their own namespaced guest bucket, so a guest can never consume (or inspect) an
    authenticated user's allocation. This is the single source of truth for that mapping -
    the pipeline and the quota endpoint must never derive it independently.
    """
    if user_id:
        return user_id
    if session_id:
        return session_id if session_id.startswith("guest") else f"guest_{session_id}"
    return "guest"


StepCallback = Callable[[str, int, float, Dict[str, Any]], None]
AcceptedCallback = Callable[[QuotaStatus], None]


def _emit(callback: Optional[Callable], *args: Any) -> None:
    """Invoke an optional observability callback without ever affecting pipeline execution.

    Callbacks are purely for external progress reporting: any exception raised by a
    callback is logged and swallowed so that an observer can never break a research run.
    """
    if callback is None:
        return
    try:
        callback(*args)
    except Exception as e:  # pragma: no cover - defensive; observers must not break runs
        logger.warning(f"Pipeline observability callback raised and was ignored: {e}")


class ResearchResult(BaseModel):
    """Container for the output of a 5-agent research pipeline execution."""
    query: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    quota_status: Optional[QuotaStatus] = None
    sub_queries: List[str] = Field(default_factory=list)
    plan_rationale: str = ""
    report: str
    search_results: List[Dict[str, Any]] = Field(default_factory=list)
    summary_output: Optional[SummaryOutput] = None
    fact_check_output: Optional[FactCheckOutput] = None
    planning_time_sec: float = 0.0
    search_time_sec: float = 0.0
    summarization_time_sec: float = 0.0
    fact_check_time_sec: float = 0.0
    synthesis_time_sec: float = 0.0
    total_time_sec: float = 0.0
    is_fallback: bool = False
    usage: Dict[str, Any] = Field(default_factory=dict)


class ResearchPipeline:
    """Five-Agent Pipeline coordinating Planner, Search, Summarizer, Fact-Checker, and Writer."""

    def __init__(
        self,
        planner_agent: Optional[PlannerAgent] = None,
        search_agent: Optional[SearchAgent] = None,
        summarizer_agent: Optional[SummarizerAgent] = None,
        fact_checker_agent: Optional[FactCheckerAgent] = None,
        writer_agent: Optional[WriterAgent] = None,
        storage: Optional[ResearchStorage] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        settings.validate_keys()
        self.planner_agent = planner_agent or PlannerAgent()
        self.search_agent = search_agent or SearchAgent()
        self.summarizer_agent = summarizer_agent or SummarizerAgent()
        self.fact_checker_agent = fact_checker_agent or FactCheckerAgent()
        self.writer_agent = writer_agent or WriterAgent()
        self.storage = storage or ResearchStorage()
        self.rate_limiter = rate_limiter or RateLimiter(storage=self.storage)

    def run(
        self,
        query: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        max_sub_queries: Optional[int] = None,
        max_results_per_subquery: Optional[int] = None,
        on_step_complete: Optional[StepCallback] = None,
        on_accepted: Optional[AcceptedCallback] = None,
    ) -> ResearchResult:
        """
        Executes the full 5-agent research loop (Plan -> Search -> Summarize -> FactCheck -> Write).
        Enforces daily query quotas and burst rate limits before any external LLM/Search calls.

        Args:
            query: The research question.
            user_id: Authenticated user identifier (enforces per-user rate limiting & isolation).
            session_id: Optional custom session identifier.
            max_sub_queries: Optional override for number of sub-queries generated by Planner.
            max_results_per_subquery: Optional override for results per sub-query.
            on_step_complete: Optional observability hook invoked as
                (step_name, step_index, elapsed_seconds, payload) after each of the five
                pipeline steps finishes. Purely informational - it cannot alter execution
                or the returned result, and exceptions it raises are logged and ignored.
            on_accepted: Optional observability hook invoked with the QuotaStatus as soon
                as the rate-limit gate has been passed and before any agent work begins.

        Returns:
            ResearchResult with plan breakdown, verified claims, cited report, and granular telemetry.
        """
        # Step 0: Validate and sanitize input query FIRST at the pipeline entry gate
        # Invalid queries (e.g. empty or >500 chars) fail immediately without consuming user quota.
        query = sanitize_user_input(query)

        # Step 1: Gate check - Enforce Rate Limiting & Quota only AFTER query is validated
        effective_user = resolve_rate_limit_identity(user_id, session_id)

        quota_status = self.rate_limiter.check_and_consume(effective_user)
        _emit(on_accepted, quota_status)
        start_total = time.perf_counter()

        # Step 1: Execute Planner Agent
        start_planning = time.perf_counter()
        plan_output, planner_usage = self.planner_agent.plan(
            query=query,
            max_sub_queries=max_sub_queries
        )
        planning_time = time.perf_counter() - start_planning
        _emit(on_step_complete, "planning", 1, round(planning_time, 2), {
            "sub_queries": list(plan_output.sub_queries),
            "rationale": plan_output.rationale,
            "is_fallback": plan_output.is_fallback,
        })

        # Step 2: Execute Search Agent (Multi-Query with Score-Based URL Deduplication)
        start_search = time.perf_counter()
        search_results = self.search_agent.search_multi(
            queries=plan_output.sub_queries,
            max_results_per_query=max_results_per_subquery
        )
        search_time = time.perf_counter() - start_search
        _emit(on_step_complete, "searching", 2, round(search_time, 2), {
            "source_count": len(search_results),
            "sources": [
                {"title": r.get("title", ""), "url": r.get("url", "")}
                for r in search_results
            ],
        })

        # Step 3: Execute Summarizer Agent (Claim Extraction & Noise Distillation)
        start_summarization = time.perf_counter()
        summary_output, summarizer_usage = self.summarizer_agent.summarize(
            search_results=search_results
        )
        summarization_time = time.perf_counter() - start_summarization
        _emit(on_step_complete, "summarizing", 3, round(summarization_time, 2), {
            "summarized_source_count": len(summary_output.sources) if summary_output else 0,
            "claim_count": sum(len(s.key_claims) for s in summary_output.sources) if summary_output else 0,
            "is_fallback": bool(summary_output.is_fallback) if summary_output else False,
        })

        # Step 4: Execute Fact-Checker Agent (Cross-Referencing & Contradiction Detection)
        start_fact_check = time.perf_counter()
        fact_check_output, fact_check_usage = self.fact_checker_agent.verify(
            query=query,
            summary_output=summary_output
        )
        fact_check_time = time.perf_counter() - start_fact_check
        _emit(on_step_complete, "fact_checking", 4, round(fact_check_time, 2), {
            "consensus_count": len(fact_check_output.consensus_facts) if fact_check_output else 0,
            "unique_count": len(fact_check_output.unique_facts) if fact_check_output else 0,
            "contradiction_count": len(fact_check_output.contradictions) if fact_check_output else 0,
            "verification_summary": fact_check_output.verification_summary if fact_check_output else "",
            "is_fallback": bool(fact_check_output.is_fallback) if fact_check_output else False,
        })

        # Step 5: Execute Writer Agent (Synthesizes Verified Claims & Flags Conflicts)
        start_synthesis = time.perf_counter()
        report, writer_usage = self.writer_agent.synthesize(
            query=query,
            search_results=search_results,
            fact_check_output=fact_check_output,
            summary_output=summary_output
        )
        synthesis_time = time.perf_counter() - start_synthesis
        _emit(on_step_complete, "writing", 5, round(synthesis_time, 2), {
            "report_chars": len(report or ""),
        })

        total_time = time.perf_counter() - start_total

        # Aggregate total token usage across all 4 LLM agents
        total_tokens = (
            planner_usage.get("total_tokens", 0) +
            summarizer_usage.get("total_tokens", 0) +
            fact_check_usage.get("total_tokens", 0) +
            writer_usage.get("total_tokens", 0)
        )

        total_usage = {
            "model": writer_usage.get("model", settings.groq_model),
            "planner_tokens": planner_usage.get("total_tokens", 0),
            "summarizer_tokens": summarizer_usage.get("total_tokens", 0),
            "fact_checker_tokens": fact_check_usage.get("total_tokens", 0),
            "writer_tokens": writer_usage.get("total_tokens", 0),
            "total_tokens": total_tokens
        }

        is_any_fallback = plan_output.is_fallback or summary_output.is_fallback or fact_check_output.is_fallback
        effective_session_id = session_id or str(uuid.uuid4())

        # Persist to database if user_id is provided
        if user_id:
            try:
                session_doc = ResearchSessionDocument(
                    session_id=effective_session_id,
                    user_id=user_id,
                    query=query,
                    plan=plan_output.sub_queries,
                    sources=search_results,
                    summaries=[s.model_dump() for s in summary_output.sources] if summary_output else [],
                    fact_check=fact_check_output.model_dump() if fact_check_output else None,
                    report=report,
                    metadata={
                        "is_fallback": is_any_fallback,
                        "execution_time_seconds": round(total_time, 2),
                        "token_usage": total_usage,
                    }
                )
                self.storage.save_session(session_doc)
            except Exception as e:
                logger.error(f"Failed to persist research session for user '{user_id}': {e}")

        return ResearchResult(
            query=query,
            user_id=user_id,
            session_id=effective_session_id if user_id else None,
            quota_status=quota_status,
            sub_queries=plan_output.sub_queries,
            plan_rationale=plan_output.rationale,
            report=report,
            search_results=search_results,
            summary_output=summary_output,
            fact_check_output=fact_check_output,
            planning_time_sec=round(planning_time, 2),
            search_time_sec=round(search_time, 2),
            summarization_time_sec=round(summarization_time, 2),
            fact_check_time_sec=round(fact_check_time, 2),
            synthesis_time_sec=round(synthesis_time, 2),
            total_time_sec=round(total_time, 2),
            is_fallback=is_any_fallback,
            usage=total_usage
        )


# Backward compatibility alias
TwoAgentPipeline = ResearchPipeline
