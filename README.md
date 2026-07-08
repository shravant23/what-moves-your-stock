# What Moves Your Stock

**Prism** — enter a ticker; get an interactive
macro exposure network map and a cited, traceable macro analysis report —
tailwinds, headwinds, what's priced in, and what would falsify the thesis.

> Prism is a research tool, not investment advice.

## How it works

1. **Extract** — the latest 10-K + two 10-Qs are pulled from SEC EDGAR and an
   LLM extracts a structured exposure profile. Every exposure must carry a
   verbatim quote, string-verified against the filing text; hallucinated
   citations are rejected.
2. **Situate** — exposures are wired into a hand-curated ~120-edge macro
   causal graph, enriched with web-sourced sector trends (each requires ≥2
   live source URLs), live FRED/World Bank macro series, and trailing price
   action for the ticker and its ETF proxies.
3. **Reason** — one reasoning pass argues both directions along real graph
   chains, producing tailwinds, headwinds, net short/long-run assessments,
   and concrete thesis breakers. Chain paths and citations are re-validated
   in code.

## Architecture

```mermaid
flowchart LR
    subgraph Frontend["Frontend — Next.js 14 + TypeScript"]
        UI["Analysis page /t/[ticker]<br/>Graph explorer /graph"]
    end

    subgraph Backend["Backend — FastAPI + SQLite"]
        API["REST API"]
        PIPE["Analysis pipeline<br/>(async jobs, staged progress)"]
        GRAPH["Causal graph<br/>(~120 curated edges)"]
        CACHE[("SQLite cache<br/>filings · macro · reports")]
    end

    subgraph Sources["Free data sources"]
        EDGAR["SEC EDGAR<br/>10-K / 10-Q"]
        FRED["FRED<br/>macro series"]
        WB["World Bank<br/>country data"]
        YF["yfinance<br/>prices"]
        LLM["Gemini LLM<br/>+ web search grounding"]
    end

    UI -->|"analyze · poll status · fetch report/graph"| API
    API --> PIPE
    PIPE <--> CACHE
    PIPE --> GRAPH
    PIPE --> EDGAR & FRED & WB & YF & LLM
```

### The analysis pipeline

```mermaid
flowchart TD
    A["POST /analyze/{ticker}"] --> B["Fetch latest 10-K + two 10-Qs<br/>(SEC EDGAR, cached forever)"]
    B --> C["LLM exposure extraction<br/>(temperature 0, schema-validated)"]
    C --> V{"Citation verifier:<br/>quote string-matches filing text?"}
    V -->|"verified"| P["Exposure profile<br/>(8–20 cited exposures)"]
    V -->|"rejected"| X["Citation stripped /<br/>exposure discarded"]
    P --> T["Web-grounded sector trends<br/>(≥2 live source URLs or discarded)"]
    P --> G["Wire company into the<br/>~120-edge causal graph"]
    T --> G
    G --> H["Enumerate candidate chains<br/>(paths ≤3 hops ending at company)"]
    M["FRED + World Bank + price action"] --> R
    H --> R["Reasoning pass<br/>(argues both directions, temp 0.3)"]
    R --> W{"Chain paths are real edges?<br/>Evidence re-verified?"}
    W -->|"valid"| REP["MacroReport<br/>tailwinds · headwinds · thesis breakers"]
    W -->|"invalid"| Y["Chain dropped"]
    REP --> K[("Cached 24h")]
```

The two diamond gates are the trust story: nothing the LLM asserts reaches the
UI unless its quotes literally appear in the filings and its causal chains are
real walks through the graph.

## Quickstart

Prereqs: Python 3.11+, Node 18+, and two **free** API keys (no credit card):

- **Google Gemini** — https://aistudio.google.com/apikey (all LLM calls)
- **FRED** — https://fred.stlouisfed.org/docs/api/api_key.html (macro series)

### 1. Backend (port 8000)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env       # then edit: set GEMINI_API_KEY and FRED_API_KEY
uvicorn app.main:app --port 8000
```

### 2. Frontend (port 3000)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 and search a ticker (try FCX). A first analysis
takes 1–3 minutes with a real staged progress screen; results are cached for
24h in `backend/prism.db`, so revisits are instant.

## Pages

- `/` — ticker search with EDGAR autocomplete
- `/t/[ticker]` — the analysis: network map (left) + cited report tabs (right).
  Click nodes for details, click edges to light up the full causal chain.
- `/graph` — the full seed causal graph, browsable standalone

## API

| Endpoint | Description |
|---|---|
| `POST /analyze/{ticker}` | Kick off analysis; returns `job_id` (idempotent, cached <24h) |
| `GET /status/{job_id}` | Real pipeline stage + percent |
| `GET /report/{ticker}` | MacroReport JSON |
| `GET /profile/{ticker}` | ExposureProfile JSON |
| `GET /graph/{ticker}` | Company subgraph (nodes + edges) |
| `GET /graph` | Full seed causal graph |
| `GET /tickers?q=` | EDGAR ticker autocomplete |

## Tests

```bash
cd backend
python -m pytest tests -q
```

37 tests cover the citation verifier (hallucination rejection), filing
section carving, seed-graph integrity, subgraph wiring (edge signs, trend
nodes, standalone exposures), reasoning-engine guardrails (invalid chain
paths dropped, unverifiable evidence stripped), cache TTL semantics, and
trend topic selection. No network or API keys required — they also run in CI
on every push.

## Acceptance scripts

```bash
cd backend
python scripts/prove_phase_a.py    # data clients: EDGAR / FRED / yfinance
python scripts/prove_phase_b.py    # exposure extraction + citation verification
python scripts/prove_phase_c.py    # seed graph + subgraph wiring
python scripts/prove_phase_c2.py   # web-grounded sector trends
python scripts/prove_phase_d.py    # full reasoning engine report
```

## Deploying a public demo (free)

The repo ships a demo mode: pre-analyzed tickers (see `backend/data/demo_cache.db`,
built with `scripts/make_demo_cache.py`) are served instantly and forever, while
analysis of new tickers is disabled — so a public instance needs **no API keys**
and can't have its LLM quota drained.

1. **Backend on Render** — New → Blueprint → select this repo. `render.yaml`
   configures everything (`DEMO_MODE=true`). Note the service URL.
2. **Frontend on Vercel** — Add New → Project → import this repo, set
   **Root Directory** to `frontend`, and add env var
   `NEXT_PUBLIC_API_URL=https://<your-render-service>.onrender.com`.

Free-tier caveat: Render spins the backend down when idle; the first visit
after a quiet spell takes ~30–60s to wake.

## Notes on the free tier

Gemini free-tier quotas are small and per-model (e.g. 20 requests/day on
`gemini-2.5-flash`). Prism ships a model ladder
(`2.5-flash → 3-flash-preview → 2.5-flash-lite`) with automatic fallback on
quota exhaustion and backoff on rate limits — expect roughly 1–2 fresh
analyses per day per key; cached tickers are unlimited. To run on Claude
instead, set `ANTHROPIC_API_KEY` and `LLM_PROVIDER=anthropic` in
`backend/.env`.
