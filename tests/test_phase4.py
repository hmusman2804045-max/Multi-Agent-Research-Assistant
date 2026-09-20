import unittest
from unittest.mock import MagicMock, patch

from src.agents.summarizer_agent import SummarizerAgent, SummaryOutput, SourceSummary
from src.agents.fact_checker_agent import FactCheckerAgent, FactCheckOutput, ConsensusFact, UniqueFact, Contradiction
from src.agents.planner_agent import PlanOutput
from src.agents.writer_agent import WriterAgent
from src.pipeline import ResearchPipeline, ResearchResult


class TestPhase4SummarizerAndFactChecker(unittest.TestCase):

    def test_summarizer_agent_extracts_claims_valid_json(self):
        summarizer = SummarizerAgent(api_key="mock_key", model="openai/gpt-oss-20b")
        mock_raw_json = (
            "{\n"
            '  "sources": [\n'
            "    {\n"
            '      "source_id": 1,\n'
            '      "title": "LLM Security Guide",\n'
            '      "url": "https://example.com/guide",\n'
            '      "key_claims": ["Prompt injection is the top LLM threat", "XML delimiters mitigate injection"],\n'
            '      "summary": "Overview of LLM security best practices."\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        mock_choice = MagicMock()
        mock_choice.message.content = mock_raw_json
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150

        summarizer.client.chat.completions.create = MagicMock(return_value=mock_response)

        mock_search_results = [
            {"title": "LLM Security Guide", "url": "https://example.com/guide", "content": "Full page text...", "score": 0.9}
        ]

        output, usage = summarizer.summarize(mock_search_results)

        self.assertIsInstance(output, SummaryOutput)
        self.assertFalse(output.is_fallback)
        self.assertEqual(len(output.sources), 1)
        self.assertEqual(output.sources[0].source_id, 1)
        self.assertEqual(len(output.sources[0].key_claims), 2)
        self.assertIn("Prompt injection is the top LLM threat", output.sources[0].key_claims)
        self.assertEqual(usage["total_tokens"], 150)

    def test_summarizer_agent_fallback_on_invalid_json(self):
        summarizer = SummarizerAgent(api_key="mock_key", model="openai/gpt-oss-20b")
        
        mock_choice = MagicMock()
        mock_choice.message.content = "I could not format this in JSON. Here is the summary."
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        summarizer.client.chat.completions.create = MagicMock(return_value=mock_response)

        mock_search_results = [
            {"title": "Fallback Source", "url": "https://fallback.com", "content": "Machine learning is fascinating and growing rapidly.", "score": 0.8}
        ]

        output, usage = summarizer.summarize(mock_search_results)

        self.assertIsInstance(output, SummaryOutput)
        self.assertTrue(output.is_fallback)
        self.assertEqual(len(output.sources), 1)
        self.assertEqual(output.sources[0].title, "Fallback Source")
        self.assertIn("Machine learning is fascinating", output.sources[0].summary)

    def test_fact_checker_agent_identifies_consensus_and_contradictions(self):
        fact_checker = FactCheckerAgent(api_key="mock_key", model="openai/gpt-oss-20b")
        mock_raw_json = (
            "{\n"
            '  "consensus_facts": [\n'
            '    {"fact": "GPT-4 was released in March 2023.", "supporting_sources": [1, 2]}\n'
            "  ],\n"
            '  "unique_facts": [\n'
            '    {"fact": "GPT-4 includes vision capabilities via GPT-4V.", "source_id": 1}\n'
            "  ],\n"
            '  "contradictions": [\n'
            "    {\n"
            '      "topic": "Parameter Count",\n'
            '      "conflict": "Source [1] claims 1.8 trillion parameters while Source [2] claims parameters were never officially disclosed.",\n'
            '      "conflicting_sources": [1, 2]\n'
            "    }\n"
            "  ],\n"
            '  "verification_summary": "High consensus on release date, but parameter counts are disputed."\n'
            "}"
        )

        mock_choice = MagicMock()
        mock_choice.message.content = mock_raw_json
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 120
        mock_response.usage.completion_tokens = 60
        mock_response.usage.total_tokens = 180

        fact_checker.client.chat.completions.create = MagicMock(return_value=mock_response)

        summary_input = SummaryOutput(sources=[
            SourceSummary(source_id=1, title="Article 1", url="https://a.com", key_claims=["Released March 2023", "1.8T params"]),
            SourceSummary(source_id=2, title="Article 2", url="https://b.com", key_claims=["Released March 2023", "Undisclosed params"])
        ])

        output, usage = fact_checker.verify("When was GPT-4 released?", summary_input)

        self.assertIsInstance(output, FactCheckOutput)
        self.assertFalse(output.is_fallback)
        self.assertEqual(len(output.consensus_facts), 1)
        self.assertEqual(output.consensus_facts[0].supporting_sources, [1, 2])
        self.assertEqual(len(output.contradictions), 1)
        self.assertEqual(output.contradictions[0].topic, "Parameter Count")
        self.assertEqual(usage["total_tokens"], 180)

    def test_fact_checker_agent_parses_non_numeric_source_ids_gracefully(self):
        fact_checker = FactCheckerAgent(api_key="mock_key", model="openai/gpt-oss-20b")
        mock_raw_json = (
            "{\n"
            '  "consensus_facts": [\n'
            '    {"fact": "Core consensus statement", "supporting_sources": ["1", "source_2", 3]}\n'
            "  ],\n"
            '  "unique_facts": [\n'
            '    {"fact": "Unique observation with string id", "source_id": "N/A"},\n'
            '    {"fact": "Second observation with valid numeric id", "source_id": 2}\n'
            "  ],\n"
            '  "contradictions": [\n'
            "    {\n"
            '      "topic": "Conflict Topic",\n'
            '      "conflict": "Source [1] states A whereas Source [2] states B",\n'
            '      "conflicting_sources": [1, 2]\n'
            "    }\n"
            "  ],\n"
            '  "verification_summary": "Full analysis completed successfully."\n'
            "}"
        )

        mock_choice = MagicMock()
        mock_choice.message.content = mock_raw_json
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        fact_checker.client.chat.completions.create = MagicMock(return_value=mock_response)

        summary_input = SummaryOutput(sources=[
            SourceSummary(source_id=1, title="Src 1", url="https://a.com", key_claims=["Claim 1"]),
            SourceSummary(source_id=2, title="Src 2", url="https://b.com", key_claims=["Claim 2"])
        ])

        output, usage = fact_checker.verify("Test Query", summary_input)

        # Must NOT fallback - all valid consensus and contradictions must be preserved!
        self.assertFalse(output.is_fallback)
        self.assertEqual(len(output.consensus_facts), 1)
        self.assertEqual(output.consensus_facts[0].supporting_sources, [1, 3])  # 'source_2' filtered safely
        self.assertEqual(len(output.unique_facts), 2)
        self.assertEqual(output.unique_facts[0].source_id, 1)  # Defaulted safely from 'N/A'
        self.assertEqual(output.unique_facts[1].source_id, 2)
        self.assertEqual(len(output.contradictions), 1)

    def test_fact_checker_agent_fallback_on_invalid_json(self):
        fact_checker = FactCheckerAgent(api_key="mock_key", model="openai/gpt-oss-20b")
        
        mock_choice = MagicMock()
        mock_choice.message.content = "Malformed non-json response."
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        fact_checker.client.chat.completions.create = MagicMock(return_value=mock_response)

        summary_input = SummaryOutput(sources=[
            SourceSummary(source_id=1, title="Src 1", url="https://src1.com", key_claims=["Claim A", "Claim B"])
        ])

        output, usage = fact_checker.verify("Test Query", summary_input)

        self.assertIsInstance(output, FactCheckOutput)
        self.assertTrue(output.is_fallback)
        self.assertEqual(len(output.unique_facts), 2)
        self.assertIn("fallback", output.verification_summary.lower())

    def test_writer_agent_formats_verified_facts_and_contradictions(self):
        writer = WriterAgent(api_key="mock_key", model="openai/gpt-oss-20b")
        fact_check = FactCheckOutput(
            consensus_facts=[
                ConsensusFact(fact="Supervised learning requires labeled data.", supporting_sources=[1, 2])
            ],
            contradictions=[
                Contradiction(
                    topic="Algorithm Superiority",
                    conflict="Source [1] favors XGBoost while Source [2] favors Isolation Forests.",
                    conflicting_sources=[1, 2]
                )
            ],
            verification_summary="Clear consensus on data requirements."
        )

        formatted_analysis = writer.format_fact_check_context(fact_check)

        self.assertIn("<verified_fact_analysis>", formatted_analysis)
        self.assertIn("<consensus_facts>", formatted_analysis)
        self.assertIn('sources="1, 2"', formatted_analysis)
        self.assertIn("Supervised learning requires labeled data.", formatted_analysis)
        self.assertIn("<flagged_contradictions>", formatted_analysis)
        self.assertIn('topic="Algorithm Superiority"', formatted_analysis)
        self.assertIn("Source [1] favors XGBoost", formatted_analysis)
        self.assertIn("</verified_fact_analysis>", formatted_analysis)

    @patch("src.pipeline.settings")
    def test_five_agent_pipeline_execution_mocked(self, mock_settings):
        mock_settings.validate_keys = MagicMock()

        mock_planner = MagicMock()
        mock_planner.plan.return_value = (
            PlanOutput(sub_queries=["Sub query 1", "Sub query 2"], rationale="Plan rationale"),
            {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}
        )

        mock_search = MagicMock()
        mock_search.search_multi.return_value = [
            {"title": "Src 1", "url": "https://src1.com", "content": "Content 1", "score": 0.9},
            {"title": "Src 2", "url": "https://src2.com", "content": "Content 2", "score": 0.85}
        ]

        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = (
            SummaryOutput(sources=[
                SourceSummary(source_id=1, title="Src 1", url="https://src1.com", key_claims=["Claim 1"]),
                SourceSummary(source_id=2, title="Src 2", url="https://src2.com", key_claims=["Claim 2"])
            ]),
            {"prompt_tokens": 80, "completion_tokens": 30, "total_tokens": 110}
        )

        mock_fact_checker = MagicMock()
        mock_fact_checker.verify.return_value = (
            FactCheckOutput(
                consensus_facts=[ConsensusFact(fact="Verified consensus", supporting_sources=[1, 2])],
                contradictions=[]
            ),
            {"prompt_tokens": 60, "completion_tokens": 25, "total_tokens": 85}
        )

        mock_writer = MagicMock()
        mock_writer.synthesize.return_value = (
            "# Summary\nVerified report content [1][2].\n\n## References\n[1] https://src1.com\n[2] https://src2.com",
            {"prompt_tokens": 150, "completion_tokens": 80, "total_tokens": 230, "model": "openai/gpt-oss-20b"}
        )

        from src.storage import ResearchStorage
        test_storage = ResearchStorage(force_mock=True, db_name="test_phase4_db")
        pipeline = ResearchPipeline(
            planner_agent=mock_planner,
            search_agent=mock_search,
            summarizer_agent=mock_summarizer,
            fact_checker_agent=mock_fact_checker,
            writer_agent=mock_writer,
            storage=test_storage,
        )

        result = pipeline.run("Explain multi-agent architecture.")

        self.assertIsInstance(result, ResearchResult)
        self.assertEqual(result.query, "Explain multi-agent architecture.")
        self.assertEqual(len(result.sub_queries), 2)
        self.assertEqual(len(result.search_results), 2)
        self.assertIsNotNone(result.summary_output)
        self.assertIsNotNone(result.fact_check_output)
        self.assertEqual(len(result.fact_check_output.consensus_facts), 1)
        self.assertIn("Verified report content", result.report)
        
        # Verify 5 distinct non-negative latencies
        self.assertGreaterEqual(result.planning_time_sec, 0.0)
        self.assertGreaterEqual(result.search_time_sec, 0.0)
        self.assertGreaterEqual(result.summarization_time_sec, 0.0)
        self.assertGreaterEqual(result.fact_check_time_sec, 0.0)
        self.assertGreaterEqual(result.synthesis_time_sec, 0.0)
        self.assertGreaterEqual(result.total_time_sec, 0.0)

        # Verify token aggregation across all 4 LLM calls (70 + 110 + 85 + 230 = 495)
        self.assertEqual(result.usage["planner_tokens"], 70)
        self.assertEqual(result.usage["summarizer_tokens"], 110)
        self.assertEqual(result.usage["fact_checker_tokens"], 85)
        self.assertEqual(result.usage["writer_tokens"], 230)
        self.assertEqual(result.usage["total_tokens"], 495)


if __name__ == "__main__":
    unittest.main()
