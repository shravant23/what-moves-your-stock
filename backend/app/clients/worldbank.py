"""World Bank API client (free, no key). Annual country-level GDP growth and
inflation for the countries in a company's geographic mix. Cached 7 days."""

from datetime import timedelta

import httpx

from ..cache import cache_get_json, cache_set_json

WB_URL = "https://api.worldbank.org/v2/country/{code}/indicator/{indicator}"
WB_TTL = timedelta(days=7)

INDICATORS = {
    "NY.GDP.MKTP.KD.ZG": "Real GDP growth (annual %)",
    "FP.CPI.TOTL.ZG": "Inflation, CPI (annual %)",
}

# Region names as they appear in filings -> World Bank country codes
_REGION_CODES = {
    "u.s.": "USA", "us": "USA", "usa": "USA", "united states": "USA",
    "north america": "USA",
    "china": "CHN",
    "indonesia": "IDN",
    "peru": "PER",
    "chile": "CHL",
    "japan": "JPN",
    "india": "IND",
    "europe": "EUU", "euro area": "EUU", "emea": "EUU",
    "south america": "ZJ", "latin america": "ZJ",  # WB aggregate: LatAm & Caribbean
    "mexico": "MEX",
    "canada": "CAN",
    "brazil": "BRA",
    "united kingdom": "GBR", "uk": "GBR",
    "germany": "DEU",
    "south korea": "KOR", "korea": "KOR",
    "taiwan": None,  # not in WB API
    "asia": "EAS", "asia pacific": "EAS",
}


def map_region(region_name: str) -> str | None:
    name = region_name.lower().strip()
    for key, code in _REGION_CODES.items():
        if key in name:
            return code
    return None


async def get_country_snapshot(client: httpx.AsyncClient, code: str) -> dict:
    """{country, gdp_growth: {year, value}, inflation: {year, value}}"""
    key = f"wb:{code}"
    cached = cache_get_json(key, WB_TTL)
    if cached is not None:
        return cached

    out: dict = {"code": code, "country": code}
    for indicator, label in INDICATORS.items():
        try:
            resp = await client.get(
                WB_URL.format(code=code, indicator=indicator),
                params={"format": "json", "per_page": 8},
                timeout=30.0,
            )
            resp.raise_for_status()
            payload = resp.json()
            rows = payload[1] if len(payload) > 1 and payload[1] else []
            latest = next((r for r in rows if r["value"] is not None), None)
            if latest:
                out["country"] = latest["country"]["value"]
                out[label] = {"year": latest["date"], "value": round(latest["value"], 2)}
        except (httpx.HTTPError, ValueError, KeyError, IndexError):
            continue
    cache_set_json(key, out)
    return out


async def get_geo_snapshots(client: httpx.AsyncClient, regions: list[str]) -> list[dict]:
    codes: list[str] = []
    for region in regions:
        code = map_region(region)
        if code and code not in codes:
            codes.append(code)
    return [await get_country_snapshot(client, c) for c in codes]
