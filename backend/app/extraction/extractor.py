"""Exposure extraction pipeline (Phase B).

Flow: EDGAR filings -> section carving -> one structured LLM call
(temperature 0, schema-validated, one retry) -> citation verification
against the full filing texts -> cached ExposureProfile."""

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from ..cache import cache_get_json, cache_set_json
from ..clients import edgar
from ..llm import call_structured
from ..models import ExposureProfile, ExtractedProfile
from .sections import carve_sections
from .verify import VerificationReport, Verifier

PROFILE_TTL = timedelta(hours=24)

SYSTEM_PROMPT = """You are a macro research analyst extracting a structured exposure profile \
from a company's SEC filings. You identify how macroeconomic forces (commodity prices, rates, \
currencies, regional demand, regulation, customer/supplier concentration) flow through to this \
specific company.

Hard rules:
- Every exposure MUST include at least one citation whose `quote` is copied VERBATIM, \
character-for-character, from the filing text provided (maximum 15 words). Never paraphrase \
inside `quote`. If you cannot find verbatim support in the text, OMIT the exposure entirely.
- `source_doc` must be exactly one of the document labels given in the input.
- Produce 8-20 exposures for a typical company, ordered most to least important.
- `rationale` is one plain-English sentence a non-finance reader understands.
- `direction` is from the company's perspective: benefits_when_up means the company benefits \
when the named factor rises.
- Never give investment advice or buy/sell language."""


def _profile_cache_key(ticker: str) -> str:
    return f"profile:{ticker.upper()}"


def _doc_label(ticker: str, filing: edgar.Filing) -> str:
    if filing.form == "10-K":
        year = filing.report_date[:4]
        return f"{ticker.upper()} 10-K FY{year}"
    return f"{ticker.upper()} 10-Q {filing.report_date}"


async def _gather_documents(
    client: httpx.AsyncClient, ticker: str
) -> tuple[str, dict[str, str], dict[str, dict[str, str]]]:
    """Returns (company_name, {label: full_text}, {label: {section: text}})."""
    _cik, company_name = await edgar.ticker_to_cik(client, ticker)
    filings = await edgar.get_target_filings(client, ticker)
    full_texts: dict[str, str] = {}
    sections: dict[str, dict[str, str]] = {}
    for filing in filings:
        label = _doc_label(ticker, filing)
        text = await edgar.get_filing_text(client, filing)
        full_texts[label] = text
        caps = (
            {"Business": 150_000, "Risk Factors": 200_000, "MD&A": 200_000}
            if filing.form == "10-K"
            else {"MD&A": 100_000, "Risk Factors": 60_000}
        )
        sections[label] = carve_sections(text, filing.form, caps)
    return company_name, full_texts, sections


def _build_user_content(
    ticker: str, company_name: str, sections: dict[str, dict[str, str]]
) -> str:
    parts = [
        f"Company: {company_name} (ticker {ticker.upper()})",
        "Extract the exposure profile from the following filing excerpts.",
        f"Valid `source_doc` labels: {list(sections.keys())}",
    ]
    for label, secs in sections.items():
        for section_name, text in secs.items():
            parts.append(
                f"\n===== DOCUMENT: {label} | SECTION: {section_name} =====\n{text}"
            )
    return "\n".join(parts)


async def extract_exposure_profile(
    ticker: str, force: bool = False, progress=None
) -> tuple[ExposureProfile, VerificationReport]:
    """Build (or return cached) verified ExposureProfile for a ticker."""
    key = _profile_cache_key(ticker)
    if not force:
        cached = cache_get_json(key, PROFILE_TTL)
        if cached is not None:
            return (
                ExposureProfile.model_validate(cached["profile"]),
                VerificationReport.model_validate(cached["report"]),
            )

    async with httpx.AsyncClient(follow_redirects=True) as client:
        company_name, full_texts, sections = await _gather_documents(client, ticker)

    if progress is not None:
        progress("extracting_profile")
    user_content = _build_user_content(ticker, company_name, sections)

    # Synchronous SDK call; keep the event loop free.
    extracted: ExtractedProfile = await asyncio.to_thread(
        call_structured, SYSTEM_PROMPT, user_content, ExtractedProfile, 0.0
    )
    if progress is not None:
        progress("verifying_citations")

    profile = ExposureProfile(
        ticker=ticker.upper(),
        company_name=company_name,
        extracted_at=datetime.now(timezone.utc),
        **extracted.model_dump(),
    )

    verifier = Verifier(full_texts)
    cleaned, report = verifier.verify_profile(profile)

    cache_set_json(
        key,
        {
            "profile": cleaned.model_dump(mode="json"),
            "report": report.model_dump(mode="json"),
        },
    )
    return cleaned, report
