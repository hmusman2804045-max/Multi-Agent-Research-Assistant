# 🤖 Multi-Agent Research Assistant

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Groq](https://img.shields.io/badge/LLM%20Inference-Groq-orange.svg)](https://groq.com/)
[![Tavily](https://img.shields.io/badge/Web%20Search-Tavily%20API-green.svg)](https://tavily.com/)
[![Phase](https://img.shields.io/badge/Status-Phase%204%20(Fact--Checked%20%26%20Verified)-success.svg)](https://github.com/hmusman2804045-max/Multi-Agent-Research-Assistant)

An autonomous multi-agent AI system designed to conduct live web research, distill factual claims, cross-reference sources, detect contradictions, and generate grounded, cited research reports with robust prompt injection defenses.

---

## 📌 Overview

Traditional LLMs hallucinate or rely on frozen training data. Unlike standard static RAG (Retrieval-Augmented Generation) which only queries pre-uploaded documents, this **Multi-Agent Research Assistant** dynamically plans research strategies, searches the live internet across multiple focused angles, extracts structured factual claims, cross-references sources to detect discrepancies, and synthesizes structured reports with inline citations.

In **Phase 4**, the system introduces two specialized intermediate agents: the **Summarizer Agent** (for noise elimination and claim extraction) and the **Fact-Checker Agent** (for cross-source validation and contradiction detection).

### Current Milestone: **Phase 4 — 5-Agent Pipeline (Plan ➔ Search ➔ Summarize ➔ Fact-Check ➔ Write)**

```
┌─────────────────────────────────────────────────────────┐
│                 User Research Question                  │
└────────────────────────────┬────────────────────────────┘
                             │ (Sanitized & Length-Capped)
                             ▼
┌─────────────────────────────────────────────────────────┐
│                   🧠 Planner Agent                      │
│   Deconstructs query into 2-4 focused sub-queries       │
│   Fenced inside <user_query> boundary tags              │
│   (Strict JSON schema validation with fallback)         │
└────────────────────────────┬────────────────────────────┘
                             │
            ┌────────────────┼────────────────┐
            ▼                ▼                ▼
     [Sub-Query 1]    [Sub-Query 2]    [Sub-Query 3]
            │                │                │
            └────────────────┼────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────┐
│                    🔍 Search Agent                      │
│     Executes Tavily searches & deduplicates by URL      │
└────────────────────────────┬────────────────────────────┘
                             │ (Deduplicated Raw Snippets)
                             ▼
┌─────────────────────────────────────────────────────────┐
│                 📝 Summarizer Agent                     │
│   - Distills key factual claims from each source        │
│   - Strips web noise, fluff, and boilerplate            │
│   - Wrapped in <untrusted_source_content> XML delimiters│
└────────────────────────────┬────────────────────────────┘
                             │ (Structured Claims & Summaries)
                             ▼
┌─────────────────────────────────────────────────────────┐
│                🔬 Fact-Checker Agent                    │
│   - Cross-references claims across all sources          │
│   - Identifies Consensus Facts (≥ 2 sources)            │
│   - Identifies Unique Facts (single source)             │
│   - Flags Contradictions & Discrepancies                │
└────────────────────────────┬────────────────────────────┘
                             │ (Verified Fact Matrix + Flagged Conflicts)
                             ▼
┌─────────────────────────────────────────────────────────┐
│                    ✍️ Writer Agent                      │
│  - Synthesizes grounded report with dedicated sections: │
│    • Summary & Key Findings                             │
│    • In-Depth Analysis                                  │
│    • Contradictions & Discrepancies (if any detected)   │
│    • Inline Bracketed Citations [1], [2]                │
└─────────────────────────────────────────────────────────┘
```

---

## 🏗️ Architecture & Core Components

- **Security & Sanitization Module (`src/security.py`)**: Validates user queries, neutralizes XML/HTML structural injections via `html.escape()`, and safely encloses untrusted web content in delimiters.
- **Planner Agent (`src/agents/planner_agent.py`)**: Analyzes research questions and produces 2–4 targeted sub-queries via deterministic JSON mode with automatic fallback.
- **Search Agent (`src/agents/search_agent.py`)**: Interacts with the **Tavily Search API** to execute multi-query searches and performs **score-based URL deduplication**.
- **Summarizer Agent (`src/agents/summarizer_agent.py`)**: Distills raw search results into structured factual claims (`key_claims`) and noise-free summaries per source.
- **Fact-Checker Agent (`src/agents/fact_checker_agent.py`)**: Cross-references claims across all sources, compiling consensus facts, single-source observations, and explicitly flagging contradictions.
- **Writer Agent (`src/agents/writer_agent.py`)**: Synthesizes verified findings into a cited markdown report, creating a dedicated **Contradictions & Discrepancies** section when conflicts are detected.
- **Pipeline Coordinator (`src/pipeline.py`)**: Orchestrates the 5-agent execution loop and captures granular latency and token telemetry across all stages.
- **Centralized Logging (`src/logger.py`)**: Structured application logging to `logs/research_assistant.log` with live colored console streaming.
- **Validated Configuration (`src/config.py`)**: Type-safe settings management using Pydantic and `python-dotenv`.

---

## 🛡️ Security & Engineering Safeguards

1. **Prompt Injection Defenses**:
   - All web content and extracted claims are framed inside `<untrusted_source_content>` and `<verified_fact_analysis>` XML blocks.
   - All attribute values (`title`, `url`, `query`) and text contents are escaped with `html.escape(quote=True)`, preventing attribute breakout and tag forging.
   - System prompts enforce strict instruction hierarchy: retrieved content is passive data and cannot override instructions.
2. **Input Validation & Capping**:
   - User queries capped at 500 characters (`MAX_QUERY_LENGTH`).
   - Snippets capped at 1,500 characters per source (`MAX_CONTENT_CHARS_PER_SOURCE`).
   - Non-printable and Unicode BIDI override characters are automatically stripped.
3. **Operational Best Practices**:
   - Zero hardcoded secrets (`.env` gitignored).
   - Exact pinned dependencies (`requirements.txt`).
   - Token budget limits (`MAX_TOKENS`, `PLANNER_MAX_TOKENS`, `SUMMARIZER_MAX_TOKENS`, `FACT_CHECKER_MAX_TOKENS`).

---

## 📊 Benchmarks & Telemetry

| Metric | Phase 1 (Single-Search) | Phase 2 (Planner + Search) | Phase 3 (Security) | Phase 4 (5-Agent Verified) | Target | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Planning Latency (Groq)** | N/A | ~0.8s – 1.2s | ~0.8s – 1.3s | ~0.8s – 1.3s | < 3.0s | ✅ Sub-second |
| **Search Latency (Tavily)** | ~0.95s – 4.0s | ~8.0s – 15.0s | ~8.0s – 14.0s | ~8.0s – 12.0s | < 20.0s | ✅ Optimal |
| **Summarization Latency (Groq)** | N/A | N/A | N/A | ~1.5s – 2.5s | < 5.0s | ✅ Fast |
| **Fact-Checking Latency (Groq)** | N/A | N/A | N/A | ~1.0s – 1.8s | < 4.0s | ✅ Fast |
| **Synthesis Latency (Groq)** | ~2.1s – 3.2s | ~1.7s – 3.5s | ~2.0s – 3.5s | ~2.5s – 4.8s | < 10.0s | ✅ Optimal |
| **Total End-to-End Latency** | **~3.15s – 7.97s** | **~10.5s – 18.0s** | **~11.0s – 17.5s** | **~14.5s – 19.5s** | **< 30.0s** | ✅ **Well within target** |
| **Cost Per Query** | **$0.00** (Free Tier) | **$0.00** (Free Tier) | **$0.00** (Free Tier) | **$0.00** (Free Tier) | $0.00 | ✅ 100% Free |

---

## 📂 Project Structure

```
Multi-Agent-Research-Assistant/
├── .gitignore               # Protection for secrets, logs, and venvs
├── .env.example             # Configuration template (includes all 5 agent settings)
├── requirements.txt         # Exact-pinned dependencies
├── main.py                  # Interactive 5-step CLI entry point
├── logs/                    # Runtime logs (gitignored)
│   └── research_assistant.log
├── src/
│   ├── __init__.py
│   ├── config.py            # Settings validation & hyperparameters
│   ├── logger.py            # Centralized logging (live console streaming + file logging)
│   ├── security.py          # Input sanitization & structural prompt injection defenses
│   ├── pipeline.py          # Five-Agent Pipeline coordinator
│   └── agents/
│       ├── __init__.py
│       ├── planner_agent.py      # Query decomposition agent
│       ├── search_agent.py       # Tavily Web Search & URL deduplication
│       ├── summarizer_agent.py   # Claim extraction & noise distillation agent
│       ├── fact_checker_agent.py # Cross-referencing & contradiction detection agent
│       └── writer_agent.py       # Shielded synthesis & grounding agent
└── tests/
    ├── test_phase1.py       # Phase 1 tests
    ├── test_phase2.py       # Phase 2 tests
    ├── test_phase3.py       # Phase 3 security & sanitization tests
    └── test_phase4.py       # Phase 4 summarization, fact-checking & 5-agent tests
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.10+
- [Groq API Key](https://console.groq.com/) (Free tier)
- [Tavily API Key](https://tavily.com/) (Free tier: 1,000 searches/month)

### 2. Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/hmusman2804045-max/Multi-Agent-Research-Assistant.git
cd Multi-Agent-Research-Assistant

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install exact dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy the example template and add your API keys:
```bash
cp .env.example .env
```
Edit `.env`:
```env
# Groq API Configuration (Free tier: https://console.groq.com/)
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-20b

# Tavily API Configuration (Free 1,000 searches/mo: https://tavily.com/)
TAVILY_API_KEY=tvly-your_tavily_api_key_here

# Pipeline Settings
MAX_SEARCH_RESULTS=5
MAX_SUB_QUERIES=3
MAX_RESULTS_PER_SUBQUERY=3

# Model Hyperparameters
TEMPERATURE=0.2
MAX_TOKENS=1024
PLANNER_TEMPERATURE=0.1
PLANNER_MAX_TOKENS=500
SUMMARIZER_TEMPERATURE=0.1
SUMMARIZER_MAX_TOKENS=1024
FACT_CHECKER_TEMPERATURE=0.1
FACT_CHECKER_MAX_TOKENS=1024

# Security & Content Limits
MAX_QUERY_LENGTH=500
MAX_CONTENT_CHARS_PER_SOURCE=1500
```

### 4. Run the Research Assistant
**Interactive CLI Mode:**
```bash
python main.py
```

**Direct Query Mode:**
```bash
python main.py -q "What was the release date of GPT-4 and what is its estimated parameter count?"
```

**Verbose Mode (Live Debug Stream):**
```bash
python main.py -v -q "Explain how gradient descent works"
```

### 5. Run Automated Tests
```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## 🗺️ Project Roadmap

- [x] **Phase 1: Two-Agent Proof of Concept** — Search Agent + Writer Agent hand-off loop.
- [x] **Phase 2: Planner Agent** — Deconstruct user queries into 2–4 targeted sub-queries with multi-search deduplication.
- [x] **Phase 3: Prompt Injection & Content Security** — Structural delimiters and sanitization of untrusted web content.
- [x] **Phase 4: Summarizer & Fact-Checker Agents** — Cross-reference sources and flag contradictions.
- [ ] **Phase 5: Authentication & User Isolation** — Firebase Auth + MongoDB Atlas with dual-key (`user_id` + `session_id`) isolation.
- [ ] **Phase 6: Rate Limiting Layer** — Per-user quota management to protect API budgets.
- [ ] **Phase 7: Frontend & Deployment** — Responsive UI deployed on Hugging Face Spaces.

---

## 📄 License
This project is licensed under the MIT License.
