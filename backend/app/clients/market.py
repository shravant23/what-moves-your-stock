"""Market prices via yfinance, cached 24h in SQLite.

yfinance is synchronous — when called from FastAPI these functions should be
wrapped in `asyncio.to_thread` (done at the call site in later phases)."""

from datetime import timedelta

import yfinance as yf
from pydantic import BaseModel

from ..cache import cache_get_json, cache_set_json

PRICE_TTL = timedelta(hours=24)

# Sector / region / commodity proxy universe (spec section 3). Companies get
# mapped to their 2-4 most relevant proxies in later phases.
SECTOR_ETFS = ["XLK", "XLE", "XLF", "XLI", "XLB", "XLV", "XLY", "XLP", "XLU", "XLRE"]
REGION_ETFS = ["FXI", "EWG", "EWJ", "EEM"]
COMMODITY_ETFS = ["CPER", "USO", "GLD", "SLV"]


class PriceSummary(BaseModel):
    symbol: str
    last_close: float | None
    as_of: str | None
    pct_1m: float | None
    pct_6m: float | None
    pct_1y: float | None


def get_price_history(symbol: str, period: str = "1y") -> dict:
    """{"dates": [...], "closes": [...]} of daily closes for the period."""
    key = f"yf:history:{symbol}:{period}"
    cached = cache_get_json(key, PRICE_TTL)
    if cached is not None:
        return cached
    df = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    history = {
        "dates": [d.strftime("%Y-%m-%d") for d in df.index],
        "closes": [round(float(c), 4) for c in df["Close"]],
    }
    cache_set_json(key, history)
    return history


def _pct(closes: list[float], trading_days_back: int) -> float | None:
    if len(closes) <= trading_days_back:
        return None
    then = closes[-1 - trading_days_back]
    if not then:
        return None
    return round((closes[-1] - then) / then * 100, 2)


def get_price_summary(symbol: str) -> PriceSummary:
    """Trailing 1m / 6m / 1y percent changes from daily closes."""
    history = get_price_history(symbol, "1y")
    closes = history["closes"]
    if not closes:
        return PriceSummary(
            symbol=symbol, last_close=None, as_of=None,
            pct_1m=None, pct_6m=None, pct_1y=None,
        )
    return PriceSummary(
        symbol=symbol,
        last_close=closes[-1],
        as_of=history["dates"][-1],
        pct_1m=_pct(closes, 21),
        pct_6m=_pct(closes, 126),
        pct_1y=_pct(closes, len(closes) - 1),
    )
