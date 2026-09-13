import logging
from typing import List, Dict, Any
from tavily import TavilyClient
from src.config import settings

logger = logging.getLogger(__name__)


class SearchAgent:
    """Agent responsible for executing live web searches via Tavily API."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.tavily_api_key
        if not self.api_key:
            raise ValueError("Tavily API key is missing. Please set TAVILY_API_KEY in .env.")
        self.client = TavilyClient(api_key=self.api_key)

    def search(self, query: str, max_results: int = None, search_depth: str = "advanced") -> List[Dict[str, Any]]:
        """
        Executes web search for a given query.

        Args:
            query: The search query string.
            max_results: Max number of results to fetch (defaults to config setting).
            search_depth: "basic" or "advanced" search depth.

        Returns:
            List of dictionaries containing title, url, content, and score.
        """
        results_limit = max_results or settings.max_search_results
        logger.info(f"Searching Tavily for query: '{query}' (limit={results_limit}, depth={search_depth})")

        try:
            response = self.client.search(
                query=query,
                search_depth=search_depth,
                max_results=results_limit,
                include_answer=True,
                include_raw_content=False
            )

            results = []
            for item in response.get("results", []):
                results.append({
                    "title": item.get("title", "No Title"),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                    "score": item.get("score", 0.0)
                })

            logger.info(f"Retrieved {len(results)} search results.")
            return results

        except Exception as e:
            logger.error(f"Search failed for query '{query}': {str(e)}")
            raise RuntimeError(f"Tavily Search API call failed: {str(e)}") from e
