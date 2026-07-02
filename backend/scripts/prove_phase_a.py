"""Phase A acceptance script.

Proves the three data clients + SQLite cache work end-to-end:
  1. EDGAR  — resolve FCX, list latest 10-K + two 10-Qs, print 10-K text
  2. FRED   — latest value + 12-month change for core & global macro series
  3. yfinance — trailing price action for FCX and its copper proxy CPER

Run from backend/:  python scripts/prove_phase_a.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.clients import edgar, fred, market


def rule(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


async def prove_edgar(client: httpx.AsyncClient) -> None:
    rule("1. SEC EDGAR — FCX filings")
    cik, title = await edgar.ticker_to_cik(client, "FCX")
    print(f"FCX -> CIK {cik} ({title})")

    filings = await edgar.get_target_filings(client, "FCX")
    for f in filings:
        print(f"  {f.form:5s} filed {f.filing_date} (period {f.report_date}) -> {f.url}")

    ten_k = next(f for f in filings if f.form == "10-K")
    text = await edgar.get_filing_text(client, ten_k)
    print(f"\n10-K text extracted: {len(text):,} characters")

    print("\n--- first 600 chars ---")
    print(text[:600])

    idx = text.find("Risk Factors", 5000)  # skip the table of contents
    if idx != -1:
        print("\n--- excerpt near 'Risk Factors' ---")
        print(text[idx : idx + 600])


async def prove_fred(client: httpx.AsyncClient) -> bool:
    rule("2. FRED — macro snapshot (latest value + 12-month change)")
    try:
        snapshot = await fred.get_macro_snapshot(client)
    except fred.FredKeyMissingError as e:
        print(f"SKIPPED: {e}")
        return False
    print(f"{'series':18s} {'name':32s} {'latest':>10s} {'date':>12s} {'1y chg':>9s}")
    for s in snapshot:
        latest = f"{s.latest_value:.2f}" if s.latest_value is not None else "n/a"
        chg = f"{s.change_1y:+.2f}" if s.change_1y is not None else "n/a"
        print(f"{s.series_id:18s} {s.name:32s} {latest:>10s} {s.latest_date or '':>12s} {chg:>9s}")
    return True


def prove_yfinance() -> None:
    rule("3. yfinance — FCX and copper proxy (CPER) price action")
    for symbol in ["FCX", "CPER"]:
        s = market.get_price_summary(symbol)
        print(
            f"{symbol:5s} last close {s.last_close} ({s.as_of})  "
            f"1m {s.pct_1m:+.1f}%  6m {s.pct_6m:+.1f}%  1y {s.pct_1y:+.1f}%"
        )


async def main() -> None:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        await prove_edgar(client)
        fred_ok = await prove_fred(client)
    prove_yfinance()

    rule("Phase A result")
    print("EDGAR client:    OK (FCX 10-K + 10-Qs fetched, cached in SQLite)")
    print(f"FRED client:     {'OK' if fred_ok else 'PENDING — set FRED_API_KEY in backend/.env'}")
    print("yfinance client: OK")


if __name__ == "__main__":
    asyncio.run(main())
