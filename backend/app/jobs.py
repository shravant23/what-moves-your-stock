"""Async analysis jobs (spec section 8).

POST /analyze/{ticker} creates a job and runs the pipeline in the background;
GET /status/{job_id} reports real stage + percent for the staged progress
screen. Idempotent: a fresh cached report (<24h) completes instantly, and a
running job for the same ticker is reused."""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .cache import cache_get_json
from .reasoning import REPORT_TTL, _report_cache_key, generate_report

STAGES: dict[str, tuple[str, int]] = {
    "queued": ("Queued…", 2),
    "fetching_filings": ("Fetching filings from EDGAR…", 8),
    "extracting_profile": ("Extracting exposure profile…", 22),
    "verifying_citations": ("Verifying citations against filings…", 38),
    "synthesizing_trends": ("Scanning current sector & global conditions…", 48),
    "pulling_macro": ("Pulling macro series and price action…", 68),
    "tracing_chains": ("Tracing causal chains through the graph…", 78),
    "writing_report": ("Writing the report…", 86),
    "done": ("Done", 100),
    "error": ("Failed", 100),
}


@dataclass
class Job:
    job_id: str
    ticker: str
    stage: str = "queued"
    status: str = "running"  # running | done | error
    error: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def as_dict(self) -> dict:
        label, percent = STAGES.get(self.stage, (self.stage, 50))
        return {
            "job_id": self.job_id,
            "ticker": self.ticker,
            "status": self.status,
            "stage": self.stage,
            "stage_label": label,
            "percent": percent,
            "error": self.error,
        }


_jobs: dict[str, Job] = {}
_running_by_ticker: dict[str, str] = {}


def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


async def _run(job: Job) -> None:
    def progress(stage: str) -> None:
        job.stage = stage

    try:
        await generate_report(job.ticker, progress=progress)
        job.stage = "done"
        job.status = "done"
    except Exception as e:
        job.stage = "error"
        job.status = "error"
        job.error = f"{type(e).__name__}: {e}"
    finally:
        _running_by_ticker.pop(job.ticker.upper(), None)


def start_analysis(ticker: str) -> Job:
    ticker = ticker.upper()

    # Fresh cached report -> instant done (idempotency rule).
    if cache_get_json(_report_cache_key(ticker), REPORT_TTL) is not None:
        job = Job(job_id=str(uuid.uuid4()), ticker=ticker, stage="done", status="done")
        _jobs[job.job_id] = job
        return job

    # Already running for this ticker -> return the same job.
    running_id = _running_by_ticker.get(ticker)
    if running_id and running_id in _jobs and _jobs[running_id].status == "running":
        return _jobs[running_id]

    job = Job(job_id=str(uuid.uuid4()), ticker=ticker)
    _jobs[job.job_id] = job
    _running_by_ticker[ticker] = job.job_id
    asyncio.get_event_loop().create_task(_run(job))
    return job
