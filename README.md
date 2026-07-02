# Prism

**See what actually moves your stock.** Enter a ticker; get an interactive
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

## Acceptance scripts

```bash
cd backend
python scripts/prove_phase_a.py    # data clients: EDGAR / FRED / yfinance
python scripts/prove_phase_b.py    # exposure extraction + citation verification
python scripts/prove_phase_c.py    # seed graph + subgraph wiring
python scripts/prove_phase_c2.py   # web-grounded sector trends
python scripts/prove_phase_d.py    # full reasoning engine report
```

## Notes on the free tier

Gemini free-tier quotas are small and per-model (e.g. 20 requests/day on
`gemini-2.5-flash`). Prism ships a model ladder
(`2.5-flash → 3-flash-preview → 2.5-flash-lite`) with automatic fallback on
quota exhaustion and backoff on rate limits — expect roughly 1–2 fresh
analyses per day per key; cached tickers are unlimited. To run on Claude
instead, set `ANTHROPIC_API_KEY` and `LLM_PROVIDER=anthropic` in
`backend/.env`.
