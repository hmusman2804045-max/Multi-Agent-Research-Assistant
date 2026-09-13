import logging
from typing import List, Dict, Any, Tuple
from groq import Groq
from src.config import settings

logger = logging.getLogger(__name__)


class WriterAgent:
    """Agent responsible for synthesizing search results into a comprehensive, cited research report."""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or settings.groq_api_key
        self.model = model or settings.groq_model
        if not self.api_key:
            raise ValueError("Groq API key is missing. Please set GROQ_API_KEY in .env.")
        self.client = Groq(api_key=self.api_key)

    def format_search_context(self, search_results: List[Dict[str, Any]], max_chars_per_source: int = 1500) -> str:
        """Formats list of search results into structured, numbered reference blocks with length capping."""
        if not search_results:
            return "No search results available."

        context_blocks = []
        for idx, item in enumerate(search_results, 1):
            title = item.get("title", "Untitled Source")
            url = item.get("url", "N/A")
            content = item.get("content", "").strip()
            # Cap snippet length to prevent exceeding LLM rate limits and token budgets
            if len(content) > max_chars_per_source:
                content = content[:max_chars_per_source] + " ... [content truncated for brevity]"

            context_blocks.append(
                f"Source [{idx}]: {title}\n"
                f"URL: {url}\n"
                f"Content: {content}\n"
            )

        return "\n---\n".join(context_blocks)

    def synthesize(self, query: str, search_results: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
        """
        Synthesizes a research report from query and search results.

        Args:
            query: The original user research question.
            search_results: List of search result dictionaries.

        Returns:
            Tuple of (synthesized markdown answer, usage metrics dict).
        """
        context = self.format_search_context(search_results)

        system_prompt = (
            "You are an expert Research Synthesis AI. Your role is to write an exhaustive, "
            "factual, objective, and well-structured research report in response to the user's question.\n\n"
            "STRICT GUIDELINES:\n"
            "1. Ground your answer ENTIRELY in the provided search results.\n"
            "2. Do NOT extrapolate or guess facts not supported by the sources.\n"
            "3. Cite sources inline using bracket numbers (e.g. [1], [2]).\n"
            "4. Structure your response with clear headings: Summary, Key Findings, In-Depth Analysis, and References.\n"
            "5. In the References section, list every cited source with its URL and Title.\n"
            "6. If the search results do not contain enough information to answer the question, clearly state the limitation."
        )

        user_content = (
            f"Research Question:\n{query}\n\n"
            f"Retrieved Search Context:\n{context}\n\n"
            f"Please synthesize the final cited research report now."
        )

        logger.info(f"Invoking Groq model '{self.model}' for synthesis...")

        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                model=self.model,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
            )

            response_text = chat_completion.choices[0].message.content
            usage = {
                "prompt_tokens": chat_completion.usage.prompt_tokens if chat_completion.usage else 0,
                "completion_tokens": chat_completion.usage.completion_tokens if chat_completion.usage else 0,
                "total_tokens": chat_completion.usage.total_tokens if chat_completion.usage else 0,
                "model": self.model
            }

            logger.info(f"Synthesis complete. Tokens used: {usage['total_tokens']}")
            return response_text, usage

        except Exception as e:
            logger.error(f"Groq synthesis failed: {str(e)}")
            raise RuntimeError(f"Groq API call failed: {str(e)}") from e
