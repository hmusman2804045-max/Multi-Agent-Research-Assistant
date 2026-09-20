# Deployment — Phase 7

The web app is one process: FastAPI serves the REST/SSE API under `/api` **and** the built
React SPA from the same origin. Because both come from one origin in production, no CORS
configuration is needed there — `CORS_ALLOW_ORIGINS` only matters for local development,
where the Vite dev server runs on its own port.

---

## 1. Run it locally

### Option A — one origin (closest to production)

```bash
cd frontend && npm install && npm run build && cd ..
python serve.py
```

Open <http://127.0.0.1:7860>. The API is at `/api`, interactive docs at `/docs`.

### Option B — two processes with hot reload (day-to-day development)

```bash
python serve.py
```

```bash
cd frontend && npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to `http://127.0.0.1:7860`, so the browser
still sees a single origin and no CORS round trips occur. If you point the frontend at a
different host instead (`VITE_API_BASE_URL`), add that origin to `CORS_ALLOW_ORIGINS`.

---

## 2. Deploy to Hugging Face Spaces

The repository is already a valid Docker Space: `README.md` carries the required YAML
frontmatter (`sdk: docker`, `app_port: 7860`) and the `Dockerfile` builds the frontend and
runs the API in one image.

### 2.1 Create the Space

1. Go to <https://huggingface.co/new-space>.
2. Give it a name, choose **Docker** → **Blank**, and pick Public or Private.
3. Leave the hardware on the free CPU tier — the app makes network calls, it does not run
   models locally.

### 2.2 Set the secrets

In **Settings → Variables and secrets**, add these as **Secrets** (not public variables):

| Secret | Required | Notes |
| --- | --- | --- |
| `GROQ_API_KEY` | yes | LLM calls for four of the five agents. |
| `TAVILY_API_KEY` | yes | Live web search. |
| `MONGODB_URI` | strongly recommended | Without it the app silently falls back to in-memory storage, so **every account and every saved report disappears on each restart**. |
| `JWT_SECRET_KEY` | strongly recommended | ≥ 32 random characters. Without it a fresh secret is generated at boot, which signs every user out on every restart. Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `RESEND_API_KEY` | optional | Only needed to actually deliver password reset emails. |

And these as public **Variables**:

| Variable | Value | Why |
| --- | --- | --- |
| `PASSWORD_RESET_LINK_BASE_URL` | `https://<user>-<space>.hf.space` | Makes reset emails carry a clickable web link instead of the CLI instruction. |
| `DAILY_QUERY_LIMIT` | e.g. `5` | Per-user daily cap. |
| `GLOBAL_DAILY_QUERY_LIMIT` | e.g. `60` | Service-wide shared cap across all users — this is what protects the Tavily free-tier budget. Set it deliberately; see §4. |
| `MONGODB_DB_NAME` | `research_assistant` | Optional. |

`CORS_ALLOW_ORIGINS` can be left unset on the Space: the SPA is served from the same origin.

### 2.3 Push

```bash
git remote add space https://huggingface.co/spaces/<your-user>/<your-space>
git push space main
```

The Space builds the Dockerfile automatically. First build takes a few minutes (Node install
plus the Python image). Watch the build log in the Space UI; when it is live, open the Space
URL and check `/api/health` returns `{"status":"ok", ...}`.

> **MongoDB Atlas network access:** Spaces do not have a fixed egress IP. Either allow
> `0.0.0.0/0` in your Atlas Network Access list, or the Space will fail to connect and fall
> back to in-memory storage (a warning appears in the log).

---

## 3. Verify the deployment

Run the Phase 7 acceptance test against the live URL. It registers two real accounts, runs
real research as each, and proves neither can see the other's history:

```bash
python scripts/verify_phase7_isolation.py --base-url https://<your-user>-<your-space>.hf.space
```

It consumes two real research runs' worth of search and LLM budget. To exercise only the auth
and isolation paths without spending quota:

```bash
python scripts/verify_phase7_isolation.py --base-url https://<your-user>-<your-space>.hf.space --skip-research
```

Delete the `acceptance_*` accounts from your database afterwards if you do not want them.

---

## 4. Budget notes

The two daily caps are different things and both matter in a public deployment:

- `DAILY_QUERY_LIMIT` is **per user**. It stops one person from draining the budget.
- `GLOBAL_DAILY_QUERY_LIMIT` is a **single shared pool across everyone**, including guests.
  It is the actual ceiling on daily Tavily spend.

One research question issues roughly `MAX_SUB_QUERIES` searches (default 3). With Tavily's
free tier at 1,000 searches/month, a `GLOBAL_DAILY_QUERY_LIMIT` of 60 implies up to ~180
searches/day — which would exhaust the month in under a week. Size it against the monthly
budget, not just against what feels generous per day.

Guests are rate limited under their own scoped bucket (`guest_web_*`, kept in the browser's
local storage), and guest runs draw from the same global pool.

---

## 5. Runtime endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/health` | — | Liveness plus the configured caps. |
| `POST` | `/api/auth/register` | — | Create an account; returns a token. |
| `POST` | `/api/auth/login` | — | Sign in; `423` with `remaining_lockout_seconds` when locked. |
| `POST` | `/api/auth/forgot-password` | — | Always the same generic `200`, whether or not the account exists. |
| `POST` | `/api/auth/reset-password` | — | Consume a single-use 15-minute token. |
| `GET` | `/api/research/stream` | optional | SSE run; works for users and guests. |
| `GET` | `/api/history` | required | List the caller's own saved sessions. |
| `GET` | `/api/history/{id}` | required | Load one saved session. |
| `DELETE` | `/api/history/{id}` | required | Delete one saved session. |
| `GET` | `/api/quota` | optional | Personal quota plus the separate service-wide cap. |

Interactive schema: `/docs`.

The API is mounted **only** under `/api`. It is deliberately not also exposed unprefixed,
because paths like `/history` are simultaneously client-side routes of the SPA served from
the same origin — an unprefixed API route would shadow them, and loading or refreshing
`/history` in a browser would return JSON instead of the app.
