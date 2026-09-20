---
title: Multi-Agent Research Assistant
emoji: 🔎
colorFrom: gray
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# 🤖 Multi-Agent Research Assistant

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Groq](https://img.shields.io/badge/LLM%20Inference-Groq-orange.svg)](https://groq.com/)
[![Tavily](https://img.shields.io/badge/Web%20Search-Tavily%20API-green.svg)](https://tavily.com/)
[![MongoDB](https://img.shields.io/badge/Database-MongoDB%20%2F%20MongoMock-brightgreen.svg)](https://www.mongodb.com/)
[![JWT](https://img.shields.io/badge/Auth-PyJWT%20(HS256)-blue.svg)](https://pyjwt.readthedocs.io/)
[![Rate Limiter](https://img.shields.io/badge/Protection-Sliding%20Window%20%2B%20Lockout-red.svg)](https://github.com/hmusman2804045-max/Multi-Agent-Research-Assistant)
[![Phase](https://img.shields.io/badge/Status-Phase%207%20(Frontend%20%26%20Deployment)-success.svg)](https://github.com/hmusman2804045-max/Multi-Agent-Research-Assistant)

An autonomous multi-agent AI system designed to conduct live web research, distill factual claims, cross-reference sources, detect contradictions, generate grounded, cited research reports, securely isolate per-user research history, and enforce robust per-user daily search quotas, sliding-window RPM burst limits, and authentication brute-force defenses.

---

## 📌 Overview

Traditional LLMs hallucinate or rely on frozen training data. Unlike standard static RAG (Retrieval-Augmented Generation) which only queries pre-uploaded documents, this **Multi-Agent Research Assistant** dynamically plans research strategies, searches the live internet across multiple focused angles, extracts structured factual claims, cross-references sources to detect discrepancies, and synthesizes structured reports with inline citations.

In **Phase 6**, the system introduces **per-user rate limiting & quota management** (`src/rate_limiter.py`) directly on top of Phase 5's authenticated identities (enforcing PRD Lesson 4):
1. **Daily Query Cap (10–15 searches/day per user)**: Protects shared Tavily API allowances.
2. **Requests-Per-Minute (RPM) Burst Limiter (3 req/min)**: Sliding-window counter protecting backend and Groq LLM inference from burst flooding.
3. **Authentication Brute-Force Defense**: Progressive lockout (5 failed attempts $\rightarrow$ 15-minute lockout) neutralizing credential-stuffing attacks.

### Current Milestone: **Phase 7 — Web Frontend, HTTP/SSE API & Deployment**

```
┌─────────────────────────────────────────────────────────┐
│        👤 Authenticated User / JWT Identity             │
└────────────────────────────┬────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│              ⏱️ Rate Limiter Entry Gate                 │
│  - Checks Burst RPM (Sliding 60-second window: ≤ 3 RPM) │
│  - Checks Daily Query Quota (≤ 10/day, resets 00:00 UTC)│
│  - Blocks exhausted requests before any agent or API hit│
└────────────────────────────┬────────────────────────────┘
                             │ (Quota Approved & Consumed)
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

- **Rate Limiting & Quota Layer (`src/rate_limiter.py`)**: Intercepts requests before any agent execution, tracking sliding 60-second burst windows, daily query caps per user, password reset request limits (3/hour), and authentication lockouts.
- **Authentication & JWT Layer (`src/auth.py`)**: Handles user registration with PBKDF2-HMAC-SHA256 password hashing (100,000 rounds, unique random salts), credential verification, constant-time comparisons, single-use password reset token lifecycle, and signed JWT session token generation/verification with algorithm whitelisting.
- **Email Delivery Subsystem (`src/email_service.py`)**: Resend REST API integration for delivering time-bounded, single-use password reset tokens with anti-enumeration protection and automatic fallback for hermetic testing.
- **Per-User Isolated Storage (`src/storage.py`)**: MongoDB / MongoMock client enforcing strict dual-key query filtering `{"user_id": user_id, "session_id": session_id}` (PRD Lesson 5). Indexes compound unique `[("user_id", 1), ("session_id", 1)]`, secondary `[("user_id", 1), ("created_at", -1)]`, `[("token", 1)]` (unique reset tokens), and `[("user_id", 1)]` for users and rate limits.
- **Security & Sanitization Module (`src/security.py`)**: Validates user queries, neutralizes XML/HTML structural injections via `html.escape(quote=True)`, and safely encloses untrusted web content in structural delimiters.
- **Planner Agent (`src/agents/planner_agent.py`)**: Analyzes research questions and produces 2–4 targeted sub-queries via deterministic JSON mode with automatic fallback.
- **Search Agent (`src/agents/search_agent.py`)**: Interacts with the **Tavily Search API** to execute multi-query searches and performs **score-based URL deduplication**.
- **Summarizer Agent (`src/agents/summarizer_agent.py`)**: Distills raw search results into structured factual claims (`key_claims`) and noise-free summaries per source.
- **Fact-Checker Agent (`src/agents/fact_checker_agent.py`)**: Cross-references claims across all sources, compiling consensus facts, single-source observations, and explicitly flagging contradictions.
- **Writer Agent (`src/agents/writer_agent.py`)**: Synthesizes verified findings into a cited markdown report, creating a dedicated **Contradictions & Discrepancies** section when conflicts are detected.
- **Pipeline Coordinator (`src/pipeline.py`)**: Orchestrates the 5-agent execution loop with pre-execution rate limiting checks, session persistence, and granular latency/token telemetry.
- **Centralized Logging (`src/logger.py`)**: Structured application logging to `logs/research_assistant.log` with live colored console streaming.
- **Validated Configuration (`src/config.py`)**: Type-safe settings management using Pydantic and `python-dotenv`.

---

## 🛡️ Security & Engineering Safeguards

1. **Per-User Rate Limiting & Quotas (PRD Lesson 4)**:
   - **Burst Protection**: Max 3 requests/minute per user (`REQUESTS_PER_MINUTE_LIMIT`) enforced via sliding 60-second window counter.
   - **Budget Protection**: Max 10 queries/day per user (`DAILY_QUERY_LIMIT`), automatically resetting at 00:00 UTC.
   - **Zero API Leakage**: When quota or burst limits are exceeded, requests are rejected immediately at the entry gate, preventing any Groq or Tavily API consumption.
2. **Authentication Brute-Force & Lockout Defense**:
   - Progressive failed login tracking (`AUTH_MAX_FAILED_ATTEMPTS=5`).
   - Temporary 15-minute account lockout (`AUTH_LOCKOUT_MINUTES=15`) upon reaching max failed attempts.
3. **Per-User Data Isolation (PRD Lesson 5)**:
   - Every read, update, or delete operation in storage strictly requires both `user_id` and `session_id`.
   - Architectural impossibility of IDOR (Insecure Direct Object Reference) vulnerabilities: User B cannot query or delete User A's session even if they know the exact `session_id`.
4. **Cryptographic JWT Authentication & Password Hashing**:
   - PBKDF2-HMAC-SHA256 password hashing with unique 16-byte random salts per user.
   - Algorithm whitelisting prevents algorithm confusion and unsigned 'none' token attacks.
   - Mandatory expiration (`exp`) and issued-at (`iat`) validation.
5. **Prompt Injection Defenses**:
   - All web content and extracted claims are framed inside `<untrusted_source_content>` and `<verified_fact_analysis>` XML blocks.
   - All attribute values (`title`, `url`, `query`) and text contents are escaped with `html.escape(quote=True)`.

---

## 📊 Benchmarks & Telemetry

| Metric | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 | Phase 6 (Rate Limited) | Target | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Planning Latency (Groq)** | N/A | ~0.8s – 1.2s | ~0.8s – 1.3s | ~0.8s – 1.3s | ~0.8s – 1.2s | ~0.8s – 1.2s | < 3.0s | ✅ Sub-second |
| **Search Latency (Tavily)** | ~0.95s – 4.0s | ~8.0s – 15.0s | ~8.0s – 14.0s | ~8.0s – 12.0s | ~8.0s – 12.5s | ~8.0s – 13.0s | < 20.0s | ✅ Optimal |
| **Summarization Latency (Groq)** | N/A | N/A | N/A | ~1.5s – 2.5s | ~1.5s – 2.7s | ~1.5s – 3.0s | < 5.0s | ✅ Fast |
| **Fact-Checking Latency (Groq)** | N/A | N/A | N/A | ~1.0s – 1.8s | ~1.0s – 2.0s | ~1.0s – 2.5s | < 4.0s | ✅ Fast |
| **Synthesis Latency (Groq)** | ~2.1s – 3.2s | ~1.7s – 3.5s | ~2.0s – 3.5s | ~2.5s – 4.8s | ~2.5s – 4.8s | ~2.5s – 4.8s | < 10.0s | ✅ Optimal |
| **Rate Limit Overhead** | N/A | N/A | N/A | N/A | N/A | **< 1ms** | < 10ms | ✅ Instant |
| **Cost Per Query** | **$0.00** | **$0.00** | **$0.00** | **$0.00** | **$0.00** | **$0.00** (Free Tier) | $0.00 | ✅ 100% Free |

---

## 📂 Project Structure

```
Multi-Agent-Research-Assistant/
├── .gitignore               # Protection for secrets, logs, and venvs
├── .env.example             # Configuration template (includes DB, JWT, Rate limits, and agent settings)
├── requirements.txt         # Exact-pinned dependencies
├── main.py                  # Interactive CLI entry point (with Auth, Rate Limiting & Quota telemetry)
├── serve.py                 # Web entry point: runs the FastAPI API + built frontend on one origin
├── Dockerfile               # Two-stage build (React -> FastAPI) for Hugging Face Spaces
├── DEPLOYMENT.md            # Local run, Hugging Face Spaces deploy, secrets & budget notes
├── logs/                    # Runtime logs (gitignored)
│   └── research_assistant.log
├── src/
│   ├── __init__.py
│   ├── rate_limiter.py      # Rate limiting, daily quota tracking, reset limiting & login lockout layer
│   ├── auth.py              # Cryptographic JWT authentication, PBKDF2 hashing & password reset logic
│   ├── email_service.py     # Resend REST API transactional email delivery service
│   ├── storage.py           # MongoDB / MongoMock dual-key isolated session, user & reset token storage
│   ├── config.py            # Settings validation & hyperparameters
│   ├── logger.py            # Centralized logging (live console streaming + file logging)
│   ├── security.py          # Input sanitization & structural prompt injection defenses
│   ├── pipeline.py          # Five-Agent Pipeline coordinator with rate limit interception
│   ├── api/                 # Thin HTTP layer over the modules above - no duplicated logic
│   │   ├── app.py           # FastAPI factory: CORS, error mapping, SPA static serving
│   │   ├── deps.py          # Shared storage/pipeline handles, auth & guest-scope dependencies
│   │   ├── errors.py        # Core exception -> HTTP status mapping (single source of truth)
│   │   ├── schemas.py       # Request/response transport models
│   │   └── routes/          # auth_routes, research_routes (SSE), history_routes, quota_routes
│   └── agents/
│       ├── __init__.py
│       ├── planner_agent.py      # Query decomposition agent
│       ├── search_agent.py       # Tavily Web Search & URL deduplication
│       ├── summarizer_agent.py   # Claim extraction & noise distillation agent
│       ├── fact_checker_agent.py # Cross-referencing & contradiction detection agent
│       └── writer_agent.py       # Shielded synthesis & grounding agent
├── frontend/                # React + Vite SPA (glassmorphic charcoal/sage UI)
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── api/client.js        # Fetch wrapper + SSE stream parser
│       ├── state/               # AuthContext (token, guest id), QuotaContext (both caps)
│       ├── components/          # Ambient background, glass primitives, progress, report view
│       └── pages/               # Landing, Auth, Forgot/Reset password, Research, History
├── scripts/
│   └── verify_phase7_isolation.py  # Live two-account cross-user isolation acceptance test
└── tests/
    ├── test_phase1.py       # Phase 1 tests
    ├── test_phase2.py       # Phase 2 tests
    ├── test_phase3.py       # Phase 3 security & sanitization tests
    ├── test_phase4.py       # Phase 4 summarization, fact-checking & 5-agent tests
    ├── test_phase5.py       # Phase 5 JWT authentication & dual-key storage isolation tests
    ├── test_phase6.py       # Phase 6 Rate limiting, quotas & brute-force lockout tests
    ├── test_password_reset.py # Password reset flow, email dispatch, anti-enumeration & token tests
    └── test_phase7_api.py   # Phase 7 HTTP API, SSE stream, rate-limit mapping & isolation tests
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
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
AUTH_TOKEN_EXPIRE_MINUTES=1440

# Rate Limiting & User Quotas (Phase 6)
DAILY_QUERY_LIMIT=10
REQUESTS_PER_MINUTE_LIMIT=3
AUTH_MAX_FAILED_ATTEMPTS=5
AUTH_LOCKOUT_MINUTES=15
```

### 4. Run the Research Assistant CLI

**Register a New User Account (with PBKDF2 Hashed Password):**
```bash
python main.py --register -u alice_researcher -p "MySecurePassword123!"
```

**Authenticate & Obtain a Signed JWT Token:**
```bash
python main.py --login -u alice_researcher -p "MySecurePassword123!"
```

**Request Password Reset Link (Anti-Enumeration Protected & Rate Limited):**
```bash
python main.py --forgot-password -u alice_researcher
```

**Confirm Password Reset with One-Time Token:**
```bash
python main.py --reset-password <RESET_TOKEN> -p "BrandNewSecurePassword123!"
```

**Check Your Real-Time Rate Limit & Daily Quota Status:**
```bash
python main.py --token <YOUR_JWT_TOKEN> --quota
```

**Run Research with Signed JWT Token (Auto-Quota Checked & Persisted):**
```bash
python main.py --token <YOUR_JWT_TOKEN> -q "What is quantum error correction surface code?"
```

**View Saved Private Research History (Authentication Required):**
```bash
python main.py --token <YOUR_JWT_TOKEN> --history
```

**Load a Specific Saved Session Report (Authentication Required):**
```bash
python main.py --token <YOUR_JWT_TOKEN> --load-session <SESSION_ID>
```

**Delete a Saved Session (Authentication Required):**
```bash
python main.py --token <YOUR_JWT_TOKEN> --delete-session <SESSION_ID>
```

**Run in Guest / Anonymous Mode (No History Saved, Subject to Guest Quotas):**
```bash
python main.py -q "Explain how gradient descent works"
```

### 5. Run the Web App (Phase 7)

Build the frontend once, then serve the API and the SPA together from one origin:

```bash
cd frontend && npm install && npm run build && cd ..
python serve.py
```

Open <http://127.0.0.1:7860>. The REST/SSE API lives under `/api` and interactive docs at `/docs`.

For frontend development with hot reload, run `python serve.py` in one shell and
`npm run dev` inside `frontend/` in another, then open <http://localhost:5173> — Vite proxies
`/api` through to the backend. Full deployment instructions, including Hugging Face Spaces and
the secrets it needs, are in [DEPLOYMENT.md](DEPLOYMENT.md).

### 6. Run Automated Tests
```bash
python -m unittest discover -s tests -p "test_*.py"
```

The Phase 7 acceptance test runs against a live server rather than a test client. It registers
two real accounts, runs real research as each, and confirms neither can list, open or delete the
other's research:

```bash
python scripts/verify_phase7_isolation.py --base-url http://127.0.0.1:7860
```

---

## 🗺️ Project Roadmap

- [x] **Phase 1: Two-Agent Proof of Concept** — Search Agent + Writer Agent hand-off loop.
- [x] **Phase 2: Planner Agent** — Deconstruct user queries into 2–4 targeted sub-queries with multi-search deduplication.
- [x] **Phase 3: Prompt Injection & Content Security** — Structural delimiters and sanitization of untrusted web content.
- [x] **Phase 4: Summarizer & Fact-Checker Agents** — Cross-reference sources and flag contradictions.
- [x] **Phase 5: Authentication & User Isolation** — Cryptographic JWT Auth + MongoDB Atlas with dual-key (`user_id` + `session_id`) isolation.
- [x] **Phase 6: Rate Limiting Layer** — Per-user quota management (10 queries/day, 3 RPM burst limit, brute-force lockout) to protect API budgets.
- [x] **Phase 7: Frontend & Deployment** — Responsive React UI over a thin FastAPI/SSE layer, deployable to Hugging Face Spaces. Verified with a live two-account cross-user isolation test.

---

## 📄 License
This project is licensed under the MIT License.
