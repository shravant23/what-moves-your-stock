"""FRED client — US core and global macro series, cached 24h.

Each series is summarized as latest value + 12-month change, which is the
shape the reasoning engine consumes."""

from datetime import date, timedelta

import httpx
from pydantic import BaseModel

from ..cache import cache_get_json, cache_set_json
from ..config import FRED_API_KEY

OBS_URL = "https://api.stlouisfed.org/fred/series/observations"
SERIES_TTL = timedelta(hours=24)

# US core series (spec section 3)
CORE_SERIES: dict[str, str] = {
    "DFF": "Fed funds rate",
    "DGS10": "10Y Treasury yield",
    "CPIAUCSL": "CPI (all urban)",
    "UNRATE": "Unemployment rate",
    "DTWEXBGS": "Broad dollar index",
    "HOUST": "Housing starts",
    "PCOPPUSDM": "Copper price (global)",
    "DCOILWTICO": "WTI crude oil",
}

# Global series (spec section 3)
GLOBAL_SERIES: dict[str, str] = {
    "DCOILBRENTEU": "Brent crude oil",
    "IRLTLT01EZM156N": "Euro area 10Y yield",
    # OECD monthly industrial-production series were discontinued on FRED in
    # 2023-24; these are the live replacements.
    "CLVMNACSCAB1GQDE": "Germany real GDP (quarterly)",
    "XTEXVA01CNM667S": "China exports (activity proxy)",
    "IRLTLT01JPM156N": "Japan 10Y yield",
}


class FredKeyMissingError(Exception):
    pass


class SeriesSummary(BaseModel):
    series_id: str
    name: str
    latest_value: float | None
    latest_date: str | None
    value_year_ago: float | None
    change_1y: float | None
    pct_change_1y: float | None


async def get_observations(
    client: httpx.AsyncClient, series_id: str, months_back: int = 15
) -> list[dict]:
    """Raw observations for the trailing window, cached 24h."""
    if not FRED_API_KEY:
        raise FredKeyMissingError(
            "FRED_API_KEY is not set — add it to backend/.env "
            "(free key: https://fred.stlouisfed.org/docs/api/api_key.html)"
        )
    key = f"fred:obs:{series_id}:{months_back}"
    cached = cache_get_json(key, SERIES_TTL)
    if cached is not None:
        return cached
    start = date.today() - timedelta(days=months_back * 31)
    resp = await client.get(
        OBS_URL,
        params={
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "observation_start": start.isoformat(),
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    obs = resp.json().get("observations", [])
    cache_set_json(key, obs)
    return obs


def _parse(obs: list[dict]) -> list[tuple[str, float]]:
    out = []
    for o in obs:
        if o["value"] not in (".", "", None):
            out.append((o["date"], float(o["value"])))
    return out


async def get_series_summary(
    client: httpx.AsyncClient, series_id: str, name: str
) -> SeriesSummary:
    """Latest value plus the value ~12 months earlier and the change between."""
    obs = _parse(await get_observations(client, series_id))
    if not obs:
        return SeriesSummary(
            series_id=series_id, name=name, latest_value=None, latest_date=None,
            value_year_ago=None, change_1y=None, pct_change_1y=None,
        )
    latest_date, latest_value = obs[-1]
    # Find the observation closest to 365 days before the latest one.
    target = date.fromisoformat(latest_date) - timedelta(days=365)
    year_ago_value = min(
        obs, key=lambda p: abs((date.fromisoformat(p[0]) - target).days)
    )[1]
    change = latest_value - year_ago_value
    pct = (change / year_ago_value * 100) if year_ago_value else None
    return SeriesSummary(
        series_id=series_id,
        name=name,
        latest_value=latest_value,
        latest_date=latest_date,
        value_year_ago=year_ago_value,
        change_1y=round(change, 4),
        pct_change_1y=round(pct, 2) if pct is not None else None,
    )


async def get_macro_snapshot(
    client: httpx.AsyncClient, series: dict[str, str] | None = None
) -> list[SeriesSummary]:
    """Summaries for a set of series (defaults to CORE + GLOBAL)."""
    if series is None:
        series = {**CORE_SERIES, **GLOBAL_SERIES}
    out: list[SeriesSummary] = []
    for sid, name in series.items():
        try:
            out.append(await get_series_summary(client, sid, name))
        except FredKeyMissingError:
            raise
        except httpx.HTTPStatusError:
            # A discontinued/renamed series shouldn't sink the snapshot.
            out.append(
                SeriesSummary(
                    series_id=sid, name=name, latest_value=None, latest_date=None,
                    value_year_ago=None, change_1y=None, pct_change_1y=None,
                )
            )
    return out
