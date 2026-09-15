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

    def search_multi(self, queries: List[str], max_results_per_query: int = None, search_depth: str = "advanced") -> List[Dict[str, Any]]:
        """
        Executes web searches across multiple sub-queries with URL-based deduplication.

        Args:
            queries: List of search sub-queries.
            max_results_per_query: Max results per sub-query (defaults to config).
            search_depth: "basic" or "advanced" search depth.

        Returns:
            Deduplicated list of search result dictionaries across all queries.
        """
        limit_per_query = max_results_per_query or settings.max_results_per_subquery
        logger.info(f"Executing multi-search across {len(queries)} sub-queries (limit={limit_per_query} each)")

        all_results = []
        seen_urls = set()

        for idx, sub_query in enumerate(queries, 1):
            try:
                sub_results = self.search(
                    query=sub_query,
                    max_results=limit_per_query,
                    search_depth=search_depth
                )

                for item in sub_results:
                    url = item.get("url", "").strip()
                    # Deduplicate by URL
                    if url and url in seen_urls:
                        logger.debug(f"Skipping duplicate URL already retrieved: {url}")
                        continue
                    if url:
                        seen_urls.add(url)
                    
                    item["matched_sub_query"] = sub_query
                    all_results.append(item)

            except Exception as e:
                logger.warning(f"Sub-query search failed for '{sub_query}': {e}. Continuing with remaining queries.")

        logger.info(f"Multi-search complete. Aggregated {len(all_results)} unique sources across {len(queries)} queries.")
        return all_results
