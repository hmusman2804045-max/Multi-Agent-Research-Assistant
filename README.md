# 🤖 Multi-Agent Research Assistant

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Groq](https://img.shields.io/badge/LLM%20Inference-Groq-orange.svg)](https://groq.com/)
[![Tavily](https://img.shields.io/badge/Web%20Search-Tavily%20API-green.svg)](https://tavily.com/)
[![MongoDB](https://img.shields.io/badge/Database-MongoDB%20%2F%20MongoMock-brightgreen.svg)](https://www.mongodb.com/)
[![JWT](https://img.shields.io/badge/Auth-PyJWT%20(HS256)-blue.svg)](https://pyjwt.readthedocs.io/)
[![Phase](https://img.shields.io/badge/Status-Phase%205%20(Auth%20%26%20User%20Isolation)-success.svg)](https://github.com/hmusman2804045-max/Multi-Agent-Research-Assistant)

An autonomous multi-agent AI system designed to conduct live web research, distill factual claims, cross-reference sources, detect contradictions, generate grounded, cited research reports, and securely isolate per-user research history using cryptographic JWT authentication and strict dual-key database queries.

---

## 📌 Overview

Traditional LLMs hallucinate or rely on frozen training data. Unlike standard static RAG (Retrieval-Augmented Generation) which only queries pre-uploaded documents, this **Multi-Agent Research Assistant** dynamically plans research strategies, searches the live internet across multiple focused angles, extracts structured factual claims, cross-references sources to detect discrepancies, and synthesizes structured reports with inline citations.

In **Phase 5**, the system introduces **cryptographic JWT authentication** (`src/auth.py`) and **strict per-user data isolation** (`src/storage.py`) using MongoDB / MongoMock with mandatory dual-key query filtering (`{"user_id": user_id, "session_id": session_id}`).

### Current Milestone: **Phase 5 — Full 5-Agent Pipeline with Auth & Per-User Isolated Storage**

```
┌─────────────────────────────────────────────────────────┐
│        👤 Authenticated User / JWT Identity             │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
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
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│              🔐 Dual-Key MongoDB Storage                │
│  - Mandatory filter: {"user_id": ..., "session_id": ...}│
│  - Prevents IDOR & cross-tenant data leakage by design  │
│  - Auto-fallback to MongoMock for local hermetic testing│
└─────────────────────────────────────────────────────────┘
```

---

## 🏗️ Architecture & Core Components

- **Authentication & JWT Layer (`src/auth.py`)**: Generates and validates signed JWT tokens, enforces strict algorithm whitelisting (preventing 'none' algorithm bypasses), verifies token expiration (`exp`) and issuance (`iat`), and extracts typed `UserIdentity`.
- **Per-User Isolated Storage (`src/storage.py`)**: MongoDB / MongoMock client enforcing strict dual-key query filtering `{"user_id": user_id, "session_id": session_id}` (PRD Lesson 5). Indexes compound unique `[("user_id", 1), ("session_id", 1)]` and secondary `[("user_id", 1), ("created_at", -1)]`.
- **Security & Sanitization Module (`src/security.py`)**: Validates user queries, neutralizes XML/HTML structural injections via `html.escape(quote=True)`, and safely encloses untrusted web content in structural delimiters.
- **Planner Agent (`src/agents/planner_agent.py`)**: Analyzes research questions and produces 2–4 targeted sub-queries via deterministic JSON mode with automatic fallback.
- **Search Agent (`src/agents/search_agent.py`)**: Interacts with the **Tavily Search API** to execute multi-query searches and performs **score-based URL deduplication**.
- **Summarizer Agent (`src/agents/summarizer_agent.py`)**: Distills raw search results into structured factual claims (`key_claims`) and noise-free summaries per source.
- **Fact-Checker Agent (`src/agents/fact_checker_agent.py`)**: Cross-references claims across all sources, compiling consensus facts, single-source observations, and explicitly flagging contradictions.
- **Writer Agent (`src/agents/writer_agent.py`)**: Synthesizes verified findings into a cited markdown report, creating a dedicated **Contradictions & Discrepancies** section when conflicts are detected.
- **Pipeline Coordinator (`src/pipeline.py`)**: Orchestrates the 5-agent execution loop, auto-persists session reports to storage, and captures granular latency and token telemetry across all stages.
- **Centralized Logging (`src/logger.py`)**: Structured application logging to `logs/research_assistant.log` with live colored console streaming.
- **Validated Configuration (`src/config.py`)**: Type-safe settings management using Pydantic and `python-dotenv`.

---

## 🛡️ Security & Engineering Safeguards

1. **Per-User Data Isolation (PRD Lesson 5)**:
   - Every read, update, or delete operation in storage strictly requires both `user_id` and `session_id`.
   - Architectural impossibility of IDOR (Insecure Direct Object Reference) vulnerabilities: User B cannot query or delete User A's session even if they know the exact `session_id`.
   - Keys are sanitized against null-byte and query injection characters.
2. **Cryptographic JWT Authentication**:
   - Algorithm whitelisting prevents algorithm confusion and unsigned 'none' token attacks.
   - Mandatory expiration (`exp`) and issued-at (`iat`) validation.
   - User identity attributes are strictly validated with Pydantic.
3. **Prompt Injection Defenses**:
   - All web content and extracted claims are framed inside `<untrusted_source_content>` and `<verified_fact_analysis>` XML blocks.
   - All attribute values (`title`, `url`, `query`) and text contents are escaped with `html.escape(quote=True)`.
   - System prompts enforce strict instruction hierarchy: retrieved content is passive data and cannot override instructions.
4. **Input Validation & Capping**:
   - User queries capped at 500 characters (`MAX_QUERY_LENGTH`).
   - Snippets capped at 1,500 characters per source (`MAX_CONTENT_CHARS_PER_SOURCE`).
   - Non-printable and Unicode BIDI override characters are automatically stripped.
5. **Operational Best Practices**:
   - Zero hardcoded secrets (`.env` gitignored).
   - Exact pinned dependencies (`requirements.txt`).
   - Graceful in-memory `mongomock` fallback when no live MongoDB connection string is provided.

---

## 📊 Benchmarks & Telemetry

| Metric | Phase 1 (Single-Search) | Phase 2 (Planner + Search) | Phase 3 (Security) | Phase 4 (5-Agent Verified) | Phase 5 (Auth & Storage) | Target | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Planning Latency (Groq)** | N/A | ~0.8s – 1.2s | ~0.8s – 1.3s | ~0.8s – 1.3s | ~0.8s – 1.2s | < 3.0s | ✅ Sub-second |
| **Search Latency (Tavily)** | ~0.95s – 4.0s | ~8.0s – 15.0s | ~8.0s – 14.0s | ~8.0s – 12.0s | ~8.0s – 12.5s | < 20.0s | ✅ Optimal |
| **Summarization Latency (Groq)** | N/A | N/A | N/A | ~1.5s – 2.5s | ~1.5s – 2.7s | < 5.0s | ✅ Fast |
| **Fact-Checking Latency (Groq)** | N/A | N/A | N/A | ~1.0s – 1.8s | ~1.0s – 2.0s | < 4.0s | ✅ Fast |
| **Synthesis Latency (Groq)** | ~2.1s – 3.2s | ~1.7s – 3.5s | ~2.0s – 3.5s | ~2.5s – 4.8s | ~2.5s – 4.8s | < 10.0s | ✅ Optimal |
| **Storage Overhead** | N/A | N/A | N/A | N/A | **< 5ms (Dual-Key indexed)** | < 50ms | ✅ Instant |
| **Cost Per Query** | **$0.00** (Free Tier) | **$0.00** (Free Tier) | **$0.00** (Free Tier) | **$0.00** (Free Tier) | **$0.00** (Free Tier) | $0.00 | ✅ 100% Free |

---

## 📂 Project Structure

```
Multi-Agent-Research-Assistant/
├── .gitignore               # Protection for secrets, logs, and venvs
├── .env.example             # Configuration template (includes DB, JWT, and agent settings)
├── requirements.txt         # Exact-pinned dependencies
├── main.py                  # Interactive CLI entry point (with Auth & Session management)
├── logs/                    # Runtime logs (gitignored)
│   └── research_assistant.log
├── src/
│   ├── __init__.py
│   ├── auth.py              # Cryptographic JWT authentication & token management
│   ├── storage.py           # MongoDB / MongoMock dual-key isolated session storage
│   ├── config.py            # Settings validation & hyperparameters
│   ├── logger.py            # Centralized logging (live console streaming + file logging)
│   ├── security.py          # Input sanitization & structural prompt injection defenses
│   ├── pipeline.py          # Five-Agent Pipeline coordinator with session persistence
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
    ├── test_phase4.py       # Phase 4 summarization, fact-checking & 5-agent tests
    └── test_phase5.py       # Phase 5 JWT authentication & dual-key storage isolation tests
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.10+
- [Groq API Key](https://console.groq.com/) (Free tier)
- [Tavily API Key](https://tavily.com/) (Free tier: 1,000 searches/month)
- (Optional) MongoDB Atlas Connection String (Falls back to in-memory `mongomock` if left blank)

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
SUMMARIZER_MAX_TOKENS=2048
FACT_CHECKER_TEMPERATURE=0.1
FACT_CHECKER_MAX_TOKENS=2048

# Security & Content Limits
MAX_QUERY_LENGTH=500
MAX_CONTENT_CHARS_PER_SOURCE=1500

# Database & Authentication (Phase 5)
MONGODB_URI=
MONGODB_DB_NAME=research_assistant
JWT_SECRET_KEY=change-this-to-a-secure-random-secret-key-at-least-32-chars
JWT_ALGORITHM=HS256
AUTH_TOKEN_EXPIRE_MINUTES=1440
```

### 4. Run the Research Assistant CLI

**Generate a Signed JWT Token:**
```bash
python main.py --generate-token alice_researcher
```

**Run Research with Authenticated User Identity:**
```bash
python main.py -u alice_researcher -q "What is quantum error correction surface code?"
```

**Run Research with Signed JWT Token:**
```bash
python main.py --token <YOUR_JWT_TOKEN> -q "Explain the latest fusion energy breakthroughs"
```

**View Saved Research History:**
```bash
python main.py -u alice_researcher --history
```

**Load a Specific Past Session Report:**
```bash
python main.py -u alice_researcher --load-session <SESSION_ID>
```

**Delete a Past Session:**
```bash
python main.py -u alice_researcher --delete-session <SESSION_ID>
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
- [x] **Phase 5: Authentication & User Isolation** — Cryptographic JWT Auth + MongoDB Atlas with dual-key (`user_id` + `session_id`) isolation.
- [ ] **Phase 6: Rate Limiting Layer** — Per-user quota management to protect API budgets.
- [ ] **Phase 7: Frontend & Deployment** — Responsive UI deployed on Hugging Face Spaces.

---

## 📄 License
This project is licensed under the MIT License.
