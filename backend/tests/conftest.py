"""Test bootstrap: point the app at a throwaway SQLite database BEFORE any
app module is imported (the engine binds to DB_PATH at import time), and
provide small model factories shared across test files."""

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ["PRISM_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "prism_test.db")

import pytest

from app.models import (  # noqa: E402  (import after env override, deliberately)
    Citation,
    DebtProfile,
    Exposure,
    ExposureProfile,
    SectorTrend,
)


def make_citation(quote: str = "we mine copper in Indonesia", doc: str = "TST 10-K FY2025") -> Citation:
    return Citation(source_doc=doc, section="Risk Factors", quote=quote)


def make_exposure(
    name: str = "Copper Prices",
    category: str = "commodity_output",
    direction: str = "benefits_when_up",
    magnitude: str = "critical",
    quote: str = "we mine copper in Indonesia",
) -> Exposure:
    return Exposure(
        name=name,
        category=category,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        magnitude=magnitude,  # type: ignore[arg-type]
        rationale=f"{name} drives results.",
        citations=[make_citation(quote)],
    )


def make_profile(exposures: list[Exposure] | None = None, ticker: str = "TST") -> ExposureProfile:
    return ExposureProfile(
        ticker=ticker,
        company_name="Test Mining Corp",
        business_summary="A test company that mines copper.",
        revenue_segments=[],
        geographic_mix=[],
        exposures=exposures if exposures is not None else [make_exposure()],
        debt_profile=DebtProfile(
            total_debt="$1 billion",
            fixed_vs_floating="90% fixed",
            rate_sensitivity_note="low",
            citation=None,
        ),
        extracted_at=datetime.now(timezone.utc),
    )


def make_trend(
    topic: str = "Copper market conditions",
    direction: str = "accelerating",
    scope: str = "global",
    source_exposure: str | None = "Copper Prices",
) -> SectorTrend:
    return SectorTrend(
        topic=topic,
        scope=scope,  # type: ignore[arg-type]
        current_state="Conditions are moving.",
        direction=direction,  # type: ignore[arg-type]
        horizon_note="Durable.",
        relevance_to_company="Matters to the company.",
        sources=["https://example.com/a", "https://example.com/b"],
        as_of=datetime.now(timezone.utc),
        source_exposure=source_exposure,
    )


@pytest.fixture
def profile() -> ExposureProfile:
    return make_profile()
