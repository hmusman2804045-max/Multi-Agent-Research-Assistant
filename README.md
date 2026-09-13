# 🤖 Multi-Agent Research Assistant

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Groq](https://img.shields.io/badge/LLM%20Inference-Groq-orange.svg)](https://groq.com/)
[![Tavily](https://img.shields.io/badge/Web%20Search-Tavily%20API-green.svg)](https://tavily.com/)
[![Phase](https://img.shields.io/badge/Status-Phase%201%20(PoC%20Verified)-success.svg)](https://github.com/hmusman2804045-max/Multi-Agent-Research-Assistant)

An autonomous multi-agent AI system designed to conduct live web research, cross-reference findings, and generate grounded, cited research reports with sub-second agent latency.

---

## 📌 Overview

Traditional LLMs hallucinate or rely on frozen training data. Unlike standard static RAG (Retrieval-Augmented Generation) which only queries pre-uploaded documents, this **Multi-Agent Research Assistant** dynamically searches the live internet, extracts relevant context, and synthesizes structured reports with inline source citations.

### Current Milestone: **Phase 1 — Two-Agent Proof of Concept**

```
┌─────────────────────────┐
│     User Research       │
│        Question         │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐      Tavily API
│      Search Agent       │ ──────────────────►  Live Web Results
└────────────┬────────────┘                     (Snippets + URLs)
             │
             ▼
┌─────────────────────────┐      Groq Engine
│      Writer Agent       │ ──────────────────►  Grounded Report
└────────────┬────────────┘     (openai/gpt-oss-20b)     with Citations
             │
             ▼
┌─────────────────────────┐
│   Structured Output     │
│   (Markdown + Sources)  │
└─────────────────────────┘
```

---

## 🏗️ Architecture & Core Components

- **Search Agent (`src/agents/search_agent.py`)**: Interacts with the **Tavily Search API** to fetch up-to-date web intelligence, extracting URLs, titles, and snippets.
- **Writer Agent (`src/agents/writer_agent.py`)**: Interfaces with **Groq**'s ultra-low latency inference engine. Employs a strict grounding prompt that forbids hallucinations and requires inline bracketed references (`[1]`, `[2]`).
- **Pipeline Coordinator (`src/pipeline.py`)**: Orchestrates the multi-agent execution loop and captures granular telemetry (search latency, synthesis latency, token consumption).
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

## 📊 Benchmarks & Telemetry (Phase 1 Baseline)

| Metric | Measured Value | Target | Status |
| :--- | :--- | :--- | :--- |
| **Search Latency (Tavily)** | ~0.95s – 4.0s | < 10.0s | ✅ Optimal |
| **Synthesis Latency (Groq)** | ~2.1s – 3.2s | < 10.0s | ✅ Optimal |
| **Total End-to-End Latency** | **~3.15s – 7.97s** | **< 30.0s** | ✅ **Well within target** |
| **Cost Per Query** | **$0.00** (Free Developer Tier) | $0.00 | ✅ 100% Free |

---

## 📂 Project Structure

```
Multi-Agent-Research-Assistant/
├── .gitignore               # Protection for secrets, logs, and venvs
├── .env.example             # Configuration template
├── requirements.txt         # Exact-pinned dependencies
├── main.py                  # CLI entry point
├── logs/                    # Runtime logs (gitignored)
│   └── research_assistant.log
├── src/
│   ├── __init__.py
│   ├── config.py            # Settings validation & loader
│   ├── logger.py            # Structured logging setup
│   ├── pipeline.py          # Two-Agent Pipeline coordinator
│   └── agents/
│       ├── __init__.py
│       ├── search_agent.py  # Tavily Web Search agent
│       └── writer_agent.py  # Groq Synthesis & Grounding agent
└── tests/
    └── test_phase1.py       # Automated unit & mock tests
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
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-20b
TAVILY_API_KEY=tvly-your_tavily_api_key_here
MAX_SEARCH_RESULTS=5
TEMPERATURE=0.2
MAX_TOKENS=1024
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
- [ ] **Phase 2: Planner Agent** — Deconstruct user queries into 2–4 targeted sub-queries.
- [ ] **Phase 3: Prompt Injection & Content Security** — Structural delimiters and sanitization of untrusted web content.
- [ ] **Phase 4: Summarizer & Fact-Checker Agents** — Cross-reference sources and flag contradictions.
- [ ] **Phase 5: Authentication & User Isolation** — Firebase Auth + MongoDB Atlas with dual-key (`user_id` + `session_id`) isolation.
- [ ] **Phase 6: Rate Limiting Layer** — Per-user quota management to protect API budgets.
- [ ] **Phase 7: Frontend & Deployment** — Responsive UI deployed on Hugging Face Spaces.

---

## 📄 License
This project is licensed under the MIT License.
