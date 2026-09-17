import unittest
from unittest.mock import MagicMock, patch
from src.config import Settings
from src.agents.planner_agent import PlanOutput
from src.agents.search_agent import SearchAgent
from src.agents.writer_agent import WriterAgent
from src.pipeline import TwoAgentPipeline, ResearchResult


class TestPhase1Pipeline(unittest.TestCase):

    def test_settings_validation_fails_on_missing_keys(self):
        settings = Settings(groq_api_key="", tavily_api_key="")
        with self.assertRaises(ValueError) as ctx:
            settings.validate_keys()
        self.assertIn("GROQ_API_KEY", str(ctx.exception))
        self.assertIn("TAVILY_API_KEY", str(ctx.exception))

    def test_writer_agent_formatting(self):
        writer = WriterAgent(api_key="mock_key", model="llama-3.1-70b-versatile")
        mock_results = [
            {"title": "Test Title 1", "url": "https://example.com/1", "content": "Sample content 1", "score": 0.95},
            {"title": "Test Title 2", "url": "https://example.com/2", "content": "Sample content 2", "score": 0.88},
        ]
        formatted = writer.format_search_context(mock_results)
        self.assertIn('<untrusted_source_content index="1"', formatted)
        self.assertIn('title="Test Title 1"', formatted)
        self.assertIn('url="https://example.com/1"', formatted)
        self.assertIn("Sample content 1", formatted)
        self.assertIn('<untrusted_source_content index="2"', formatted)
        self.assertIn('title="Test Title 2"', formatted)

    @patch("src.pipeline.settings")
    def test_two_agent_pipeline_execution_mocked(self, mock_settings):
        mock_settings.validate_keys = MagicMock()

        mock_search_agent = MagicMock()
        mock_search_agent.search.return_value = [
            {"title": "AI Advancements", "url": "https://ai.example.com", "content": "AI is advancing rapidly.", "score": 0.9}
        ]
        mock_search_agent.search_multi.return_value = [
            {"title": "AI Advancements", "url": "https://ai.example.com", "content": "AI is advancing rapidly.", "score": 0.9}
        ]

        mock_writer_agent = MagicMock()
        mock_writer_agent.synthesize.return_value = (
            "## Summary\nAI is advancing rapidly [1].\n\n## References\n[1] https://ai.example.com",
            {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80, "model": "llama-3.1-70b-versatile"}
        )

        mock_planner_agent = MagicMock()
        mock_planner_agent.plan.return_value = (
            PlanOutput(sub_queries=["What are the latest AI advancements?"], rationale="Direct query"),
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        )

        pipeline = TwoAgentPipeline(
            planner_agent=mock_planner_agent,
            search_agent=mock_search_agent,
            writer_agent=mock_writer_agent
        )
        result = pipeline.run("What are the latest AI advancements?")

        self.assertIsInstance(result, ResearchResult)
        self.assertEqual(result.query, "What are the latest AI advancements?")
        self.assertIn("AI is advancing rapidly", result.report)
        self.assertEqual(len(result.search_results), 1)
        self.assertGreaterEqual(result.total_time_sec, 0.0)
        self.assertEqual(result.usage["total_tokens"], 80)


if __name__ == "__main__":
    unittest.main()
