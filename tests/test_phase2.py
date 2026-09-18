import unittest
from unittest.mock import MagicMock, patch
from src.agents.planner_agent import PlannerAgent, PlanOutput
from src.agents.summarizer_agent import SummaryOutput
from src.agents.fact_checker_agent import FactCheckOutput
from src.agents.search_agent import SearchAgent
from src.pipeline import ResearchPipeline, ResearchResult


class TestPhase2PlannerAndMultiSearch(unittest.TestCase):

    def test_planner_agent_parse_valid_json(self):
        planner = PlannerAgent(api_key="mock_key", model="openai/gpt-oss-20b")
        valid_json = (
            '{\n'
            '  "sub_queries": ["supervised vs unsupervised learning", "machine learning for fraud detection"],\n'
            '  "rationale": "Separates theory from applied fraud detection context."\n'
            '}'
        )
        plan = planner._parse_response(valid_json, "fallback query", limit=3)
        self.assertIsInstance(plan, PlanOutput)
        self.assertEqual(len(plan.sub_queries), 2)
        self.assertEqual(plan.sub_queries[0], "supervised vs unsupervised learning")
        self.assertEqual(plan.sub_queries[1], "machine learning for fraud detection")
        self.assertIn("Separates theory", plan.rationale)

    def test_planner_agent_parse_fallback_on_invalid_json(self):
        planner = PlannerAgent(api_key="mock_key", model="openai/gpt-oss-20b")
        invalid_content = "Here are the queries: 1. query one 2. query two"
        plan = planner._parse_response(invalid_content, "original question", limit=3)
        self.assertIsInstance(plan, PlanOutput)
        self.assertEqual(plan.sub_queries, ["original question"])
        self.assertIn("Fallback", plan.rationale)

    def test_search_agent_multi_search_deduplication(self):
        search_agent = SearchAgent(api_key="mock_key")
        
        # Mock search method to return overlapping results across 2 sub-queries
        search_agent.search = MagicMock(side_effect=[
            [
                {"title": "Doc A", "url": "https://example.com/shared", "content": "Shared content", "score": 0.9},
                {"title": "Doc B", "url": "https://example.com/doc-b", "content": "Doc B content", "score": 0.8},
            ],
            [
                {"title": "Doc A (Duplicate)", "url": "https://example.com/shared", "content": "Duplicate content", "score": 0.95},
                {"title": "Doc C", "url": "https://example.com/doc-c", "content": "Doc C content", "score": 0.85},
            ]
        ])

        results = search_agent.search_multi(["query 1", "query 2"], max_results_per_query=2)

        # Should deduplicate https://example.com/shared and return 3 total unique items, retaining highest-scored version
        self.assertEqual(len(results), 3)
        unique_urls = [r["url"] for r in results]
        self.assertEqual(unique_urls, ["https://example.com/shared", "https://example.com/doc-b", "https://example.com/doc-c"])
        # Verify higher-scored Doc A (0.95 from query 2) replaced the lower-scored one (0.9 from query 1)
        self.assertEqual(results[0]["score"], 0.95)
        self.assertEqual(results[0]["title"], "Doc A (Duplicate)")
        self.assertEqual(results[0]["matched_sub_query"], "query 2")
        self.assertEqual(results[2]["matched_sub_query"], "query 2")

    @patch("src.pipeline.settings")
    def test_three_agent_pipeline_execution_mocked(self, mock_settings):
        mock_settings.validate_keys = MagicMock()
        mock_settings.groq_model = "openai/gpt-oss-20b"

        mock_planner = MagicMock()
        mock_planner.plan.return_value = (
            PlanOutput(
                sub_queries=["Sub query 1", "Sub query 2"],
                rationale="Test rationale"
            ),
            {"prompt_tokens": 40, "completion_tokens": 20, "total_tokens": 60}
        )

        mock_search = MagicMock()
        mock_search.search_multi.return_value = [
            {"title": "Result 1", "url": "https://example.com/1", "content": "Content 1", "score": 0.9},
            {"title": "Result 2", "url": "https://example.com/2", "content": "Content 2", "score": 0.85}
        ]

        mock_writer = MagicMock()
        mock_writer.synthesize.return_value = (
            "## Summary\nComprehensive synthesized answer [1][2].\n\n## References\n[1] https://example.com/1",
            {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "model": "openai/gpt-oss-20b"}
        )

        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = (SummaryOutput(sources=[], is_fallback=False), {"total_tokens": 0})

        mock_fact_checker = MagicMock()
        mock_fact_checker.verify.return_value = (FactCheckOutput(consensus_facts=[], unique_facts=[], contradictions=[], is_fallback=False), {"total_tokens": 0})

        pipeline = ResearchPipeline(
            planner_agent=mock_planner,
            search_agent=mock_search,
            summarizer_agent=mock_summarizer,
            fact_checker_agent=mock_fact_checker,
            writer_agent=mock_writer
        )

        result = pipeline.run("Complex multi-part question")

        self.assertIsInstance(result, ResearchResult)
        self.assertEqual(result.query, "Complex multi-part question")
        self.assertEqual(len(result.sub_queries), 2)
        self.assertEqual(len(result.search_results), 2)
        self.assertIn("Comprehensive synthesized answer", result.report)
        self.assertGreaterEqual(result.total_time_sec, 0.0)
        self.assertEqual(result.usage["total_tokens"], 210)  # 60 + 150


if __name__ == "__main__":
    unittest.main()
