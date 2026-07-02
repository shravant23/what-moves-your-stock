"""FastAPI app. Endpoints grow phase by phase; analyze/status/report land
with the async pipeline in Phase D/E."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .cache import cache_get_json
from .causal_graph import build_subgraph, get_full_graph, persist_seed
from .config import FRONTEND_ORIGIN
from .db import init_db
from .extraction.extractor import PROFILE_TTL, _profile_cache_key
from .models import ExposureProfile, Graph, MacroReport
from .reasoning import REPORT_TTL, _report_cache_key

app = FastAPI(title="Prism API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # Cover the common local-dev origins (Next falls back to 3001 when 3000
    # is taken, and Safari/Chrome may use 127.0.0.1 instead of localhost).
    allow_origins=list(
        {
            FRONTEND_ORIGIN,
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
        }
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()
    persist_seed()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/tickers")
async def search_tickers(q: str = "") -> list[dict]:
    """Autocomplete against the EDGAR ticker list."""
    import httpx

    from .clients.edgar import get_ticker_map

    q = q.strip().upper()
    if not q:
        return []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        mapping = await get_ticker_map(client)
    starts = [
        {"ticker": t, "title": info["title"]}
        for t, info in mapping.items()
        if t.startswith(q)
    ]
    contains = [
        {"ticker": t, "title": info["title"]}
        for t, info in mapping.items()
        if q in info["title"].upper() and not t.startswith(q)
    ]
    return (starts + contains)[:10]


@app.post("/analyze/{ticker}")
async def analyze(ticker: str) -> dict:
    """Kick off (or reuse) the async analysis pipeline. Returns a job_id to
    poll via GET /status/{job_id}. Instant-done when a fresh report exists."""
    import httpx

    from .clients.edgar import TickerNotFoundError, ticker_to_cik
    from .jobs import start_analysis

    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            await ticker_to_cik(client, ticker)
        except TickerNotFoundError:
            raise HTTPException(
                status_code=404, detail=f"Ticker {ticker.upper()!r} not found in EDGAR."
            )
    return start_analysis(ticker).as_dict()


@app.get("/status/{job_id}")
def job_status(job_id: str) -> dict:
    from .jobs import get_job

    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id.")
    return job.as_dict()


def _load_profile(ticker: str) -> ExposureProfile:
    cached = cache_get_json(_profile_cache_key(ticker), PROFILE_TTL)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis found for {ticker.upper()}. Run POST /analyze/{ticker} first.",
        )
    return ExposureProfile.model_validate(cached["profile"])


@app.get("/profile/{ticker}")
def get_profile(ticker: str) -> ExposureProfile:
    return _load_profile(ticker)


@app.get("/report/{ticker}")
def get_report(ticker: str) -> MacroReport:
    cached = cache_get_json(_report_cache_key(ticker), REPORT_TTL)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=f"No report found for {ticker.upper()}. Run POST /analyze/{ticker} first.",
        )
    return MacroReport.model_validate(cached["report"])


@app.get("/graph")
def full_graph() -> Graph:
    """The complete seed causal graph (for the /graph explorer page)."""
    return get_full_graph()


@app.get("/graph/{ticker}")
def ticker_graph(ticker: str) -> Graph:
    """Company-centered subgraph for the analysis page visualization.
    Includes sector-trend nodes when the trend layer has been generated."""
    from .trends import get_cached_trends

    return build_subgraph(_load_profile(ticker), trends=get_cached_trends(ticker))
