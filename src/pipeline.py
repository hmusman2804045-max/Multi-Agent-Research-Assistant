import time
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from src.config import settings
from src.agents.search_agent import SearchAgent
from src.agents.writer_agent import WriterAgent

logger = logging.getLogger(__name__)


class ResearchResult(BaseModel):
    """Container for the output of a research pipeline execution."""
    query: str
    report: str
    search_results: List[Dict[str, Any]]
    search_time_sec: float
    synthesis_time_sec: float
    total_time_sec: float
    usage: Dict[str, Any] = Field(default_factory=dict)


class TwoAgentPipeline:
    """Proof-of-Concept Pipeline coordinating SearchAgent and WriterAgent."""

    def __init__(self, search_agent: Optional[SearchAgent] = None, writer_agent: Optional[WriterAgent] = None):
        settings.validate_keys()
        self.search_agent = search_agent or SearchAgent()
        self.writer_agent = writer_agent or WriterAgent()

    def run(self, query: str, max_search_results: Optional[int] = None) -> ResearchResult:
        """
        Executes the full 2-agent research loop.

        Args:
            query: The research question.
            max_search_results: Optional override for number of search results.

        Returns:
            ResearchResult with cited markdown report and latency breakdown.
        """
        if not query or not query.strip():
            raise ValueError("Research query cannot be empty.")

        query = query.strip()
        start_total = time.perf_counter()

        # 1. Execute Search Agent
        start_search = time.perf_counter()
        search_results = self.search_agent.search(query=query, max_results=max_search_results)
        search_time = time.perf_counter() - start_search

        # 2. Execute Writer Agent
        start_synthesis = time.perf_counter()
        report, usage = self.writer_agent.synthesize(query=query, search_results=search_results)
        synthesis_time = time.perf_counter() - start_synthesis

        total_time = time.perf_counter() - start_total

        return ResearchResult(
            query=query,
            report=report,
            search_results=search_results,
            search_time_sec=round(search_time, 2),
            synthesis_time_sec=round(synthesis_time, 2),
            total_time_sec=round(total_time, 2),
            usage=usage
        )
