"""Sector & global trend layer (spec section 5b).

For each of the company's top exposure categories (cap 6), run a two-step
synthesis: (1) a web-grounded research call whose source URLs come from
search grounding metadata, (2) a structured formatting call into the
SectorTrend schema. Trends with fewer than 2 live source URLs are discarded.
Cached 24h per ticker."""

import asyncio
import re
from datetime import date, datetime, timedelta, timezone

import httpx

from .cache import cache_get_json, cache_set_json
from .llm import call_grounded_search, call_structured
from .models import Exposure, ExposureProfile, SectorTrend, SectorTrendLLM

TREND_TTL = timedelta(hours=24)
MAX_TRENDS = 6

_MAGNITUDE_RANK = {"critical": 0, "significant": 1, "moderate": 2, "minor": 3}

SEARCH_PROMPT = """Research the CURRENT state (as of {today}) of the following macro/sector driver \
and how it is evolving globally:

DRIVER: {topic}
CONTEXT: This driver matters to {company} ({ticker}). {rationale}

Search the web for recent conditions. Cover:
1. Present conditions (prices, supply/demand balance, activity levels) with concrete figures
2. Whether the driver is accelerating, stable, decelerating, or inflecting — and why
3. How durable the trend looks over the next 1-2 years
4. Non-US developments where relevant (China, Europe, emerging markets)

Prefer recent primary and industry sources. If sources disagree, state the disagreement \
explicitly ("estimates range from X to Y") — do not average it away."""

FORMAT_SYSTEM = """You convert macro research notes into a structured trend object. \
Be faithful to the research text: no new claims, keep concrete figures, preserve stated \
disagreements between sources. `current_state` is 2-3 sentences about present conditions only. \
`scope` is where the dominant dynamics are playing out. No investment advice."""


def _trends_cache_key(ticker: str) -> str:
    return f"trends:{ticker.upper()}"


def select_trend_exposures(profile: ExposureProfile) -> list[Exposure]:
    """Top exposures, most important first, one per category, capped."""
    ranked = sorted(profile.exposures, key=lambda e: _MAGNITUDE_RANK[e.magnitude])
    seen: set[str] = set()
    picked: list[Exposure] = []
    for exposure in ranked:
        if exposure.category in seen:
            continue
        seen.add(exposure.category)
        picked.append(exposure)
        if len(picked) >= MAX_TRENDS:
            break
    return picked


def _resolve_url(url: str) -> str:
    """Grounding URIs are redirect links; resolve to the real page when possible."""
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=8.0)
        return str(resp.url)
    except Exception:
        return url


def _synthesize_trend(profile: ExposureProfile, exposure: Exposure) -> SectorTrend | None:
    research, urls = call_grounded_search(
        SEARCH_PROMPT.format(
            today=date.today().isoformat(),
            topic=exposure.name,
            company=profile.company_name,
            ticker=profile.ticker,
            rationale=exposure.rationale,
        )
    )
    if len(urls) < 2 or not research.strip():
        return None  # rule: no trend without at least 2 sources

    resolved = [_resolve_url(u) for u in urls[:5]]

    formatted = call_structured(
        FORMAT_SYSTEM,
        f"Company: {profile.company_name} ({profile.ticker})\n"
        f"Driver researched: {exposure.name}\n\nRESEARCH NOTES:\n{research}",
        SectorTrendLLM,
        temperature=0.0,
        max_tokens=4000,
    )
    return SectorTrend(
        **formatted.model_dump(),
        sources=resolved,
        as_of=datetime.now(timezone.utc),
        source_exposure=exposure.name,
    )


async def get_sector_trends(
    profile: ExposureProfile, force: bool = False
) -> list[SectorTrend]:
    key = _trends_cache_key(profile.ticker)
    if not force:
        cached = cache_get_json(key, TREND_TTL)
        if cached is not None:
            return [SectorTrend.model_validate(t) for t in cached]

    trends: list[SectorTrend] = []
    for exposure in select_trend_exposures(profile):
        topic_key = f"{key}:{re.sub(r'[^a-z0-9]+', '_', exposure.name.lower())}"
        cached_topic = None if force else cache_get_json(topic_key, TREND_TTL)
        if cached_topic is not None:
            trends.append(SectorTrend.model_validate(cached_topic))
            continue
        try:
            trend = await asyncio.to_thread(_synthesize_trend, profile, exposure)
        except Exception as e:  # one failed topic must not sink the layer
            print(f"[trends] {exposure.name}: skipped ({type(e).__name__}: {str(e)[:120]})")
            continue
        if trend is not None:
            cache_set_json(topic_key, trend.model_dump(mode="json"))
            trends.append(trend)

    cache_set_json(key, [t.model_dump(mode="json") for t in trends])
    return trends


def get_cached_trends(ticker: str) -> list[SectorTrend]:
    cached = cache_get_json(_trends_cache_key(ticker), TREND_TTL)
    return [SectorTrend.model_validate(t) for t in cached] if cached else []


def trend_slug(trend: SectorTrend) -> str:
    return re.sub(r"[^a-z0-9]+", "_", trend.topic.lower()).strip("_")[:48]
