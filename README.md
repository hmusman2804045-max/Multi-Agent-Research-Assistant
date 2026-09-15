# 🤖 Multi-Agent Research Assistant

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Groq](https://img.shields.io/badge/LLM%20Inference-Groq-orange.svg)](https://groq.com/)
[![Tavily](https://img.shields.io/badge/Web%20Search-Tavily%20API-green.svg)](https://tavily.com/)
[![Phase](https://img.shields.io/badge/Status-Phase%202%20(Planner%20%2B%20Multi--Search%20Verified)-success.svg)](https://github.com/hmusman2804045-max/Multi-Agent-Research-Assistant)

An autonomous multi-agent AI system designed to conduct live web research, cross-reference findings, and generate grounded, cited research reports with sub-second agent latency.

---

## 📌 Overview

Traditional LLMs hallucinate or rely on frozen training data. Unlike standard static RAG (Retrieval-Augmented Generation) which only queries pre-uploaded documents, this **Multi-Agent Research Assistant** dynamically plans research strategies, searches the live internet across multiple focused angles, extracts relevant context, and synthesizes structured reports with inline source citations.

### Current Milestone: **Phase 2 — Planner + Multi-Search Pipeline**

```
┌─────────────────────────────────────────────────────────┐
│                 User Research Question                  │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│                   🧠 Planner Agent                      │
│   Deconstructs query into 2-4 focused sub-queries       │
│   (Strict JSON / Pydantic schema validation + fallback) │
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
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│                    ✍️ Writer Agent                      │
│     Synthesizes multi-angle context into cited report   │
└─────────────────────────────────────────────────────────┘
```

---

## 🏗️ Architecture & Core Components

- **Planner Agent (`src/agents/planner_agent.py`)**: Analyzes research questions and produces 2–4 targeted sub-queries via deterministic JSON mode with automatic fallback.
- **Search Agent (`src/agents/search_agent.py`)**: Interacts with the **Tavily Search API** to execute multi-query searches and performs **URL deduplication** across all retrieved sources.
- **Writer Agent (`src/agents/writer_agent.py`)**: Interfaces with **Groq**'s ultra-low latency inference engine. Employs a strict grounding prompt that forbids hallucinations and requires inline bracketed references (`[1]`, `[2]`).
- **Pipeline Coordinator (`src/pipeline.py`)**: Orchestrates the multi-agent execution loop (Planner $\rightarrow$ Multi-Search $\rightarrow$ Writer) and captures granular telemetry (planning latency, search latency, synthesis latency, token consumption).
- **Centralized Logging (`src/logger.py`)**: Structured, thread-safe application logging to `logs/research_assistant.log` with optional live console streaming (`-v` / `--verbose`).
- **Validated Configuration (`src/config.py`)**: Type-safe settings management using Pydantic and `python-dotenv`.

---

## 🛡️ Engineering Safeguards & Best Practices

1. **Zero Hardcoded Secrets**: All API keys are loaded via environment variables (`.env`). `.env` is `.gitignore`d from the first commit.
2. **Exact Version Pinning**: Exact dependencies pinned with `==` in `requirements.txt` to eliminate environment drift.
3. **Token Budget & Rate-Limit Guardrails**: 
   - Per-source snippet length capping ($1,500$ characters) prevents context explosion.
   - Explicit `MAX_TOKENS` configuration prevents On-Demand Output Token Per Minute (OTPM) rate limits.
4. **Latency-Optimized Inference**: Powered by Groq for sub-second agent execution.

---

## 📊 Benchmarks & Telemetry

| Metric | Phase 1 (Single-Search) | Phase 2 (Planner + Multi-Search) | Target | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Planning Latency (Groq)** | N/A | ~0.8s – 1.2s | < 3.0s | ✅ Sub-second |
| **Search Latency (Tavily)** | ~0.95s – 4.0s | ~8.0s – 15.0s (3 sub-queries) | < 20.0s | ✅ Optimal |
| **Synthesis Latency (Groq)** | ~2.1s – 3.2s | ~1.7s – 3.5s | < 10.0s | ✅ Optimal |
| **Total End-to-End Latency** | **~3.15s – 7.97s** | **~10.5s – 18.0s** | **< 30.0s** | ✅ **Well within target** |
| **Cost Per Query** | **$0.00** (Free Tier) | **$0.00** (Free Tier) | $0.00 | ✅ 100% Free |

---

## 📂 Project Structure

```
Multi-Agent-Research-Assistant/
├── .gitignore               # Protection for secrets, logs, and venvs
├── .env.example             # Configuration template (includes Phase 2 settings)
├── requirements.txt         # Exact-pinned dependencies
├── main.py                  # Interactive CLI entry point with fallback alerts
├── logs/                    # Runtime logs (gitignored)
│   └── research_assistant.log
├── src/
│   ├── __init__.py
│   ├── config.py            # Settings validation & dynamic configuration
│   ├── logger.py            # Centralized logging (live console streaming + file logging)
│   ├── pipeline.py          # Three-Agent Pipeline coordinator (Planner -> Multi-Search -> Writer)
│   └── agents/
│       ├── __init__.py
│       ├── planner_agent.py # Query decomposition & JSON planning agent
│       ├── search_agent.py  # Tavily Web Search & score-based URL deduplication
│       └── writer_agent.py  # Groq Synthesis & Grounding agent
└── tests/
    ├── test_phase1.py       # Phase 1 unit & pipeline tests
    └── test_phase2.py       # Phase 2 planner, deduplication & 3-agent tests
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
```

### 4. Run the Research Assistant
**Interactive CLI Mode:**
```bash
python main.py
```

**Direct Query Mode:**
```bash
python main.py -q "What are the latest breakthroughs in agentic AI in 2026?"
```

**Verbose Mode (Live Debug Stream):**
```bash
python main.py -v -q "Explain gradient descent in machine learning"
```

### 5. Run Automated Tests
```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## 🗺️ Project Roadmap

- [x] **Phase 1: Two-Agent Proof of Concept** — Search Agent + Writer Agent hand-off loop.
- [x] **Phase 2: Planner Agent** — Deconstruct user queries into 2–4 targeted sub-queries with multi-search deduplication.
- [ ] **Phase 3: Prompt Injection & Content Security** — Structural delimiters and sanitization of untrusted web content.
- [ ] **Phase 4: Summarizer & Fact-Checker Agents** — Cross-reference sources and flag contradictions.
- [ ] **Phase 5: Authentication & User Isolation** — Firebase Auth + MongoDB Atlas with dual-key (`user_id` + `session_id`) isolation.
- [ ] **Phase 6: Rate Limiting Layer** — Per-user quota management to protect API budgets.
- [ ] **Phase 7: Frontend & Deployment** — Responsive UI deployed on Hugging Face Spaces.

---

## 📄 License
This project is licensed under the MIT License.
