"""Phase D acceptance script (spec 9.2 + 9.2b).

Generates the full MacroReport for FCX in the terminal and checks:
  - at least one multi-hop chain (path length >= 3 nodes)
  - both tailwinds AND headwinds present
  - a priced_in_note referencing real price numbers
  - report incorporates >=2 sector trends (each with >=2 source URLs)
  - at least one chain rests on a NON-US condition

Run from backend/:  python scripts/prove_phase_d.py [TICKER] [--force]
"""

import asyncio
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import Chain
from app.reasoning import generate_report
from app.trends import get_cached_trends

NON_US_NODES = {
    "china_growth", "china_property", "indonesia_policy_risk",
    "latam_political_risk", "europe_growth", "japan_growth",
    "em_growth", "india_growth", "em_currencies",
}


def rule(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def show_chain(c: Chain) -> None:
    print(f"\n  [{c.strength.upper():8s} | {c.horizon}] {' -> '.join(c.path)}")
    print(f"  {c.explanation}")
    print(f"  priced in? {c.priced_in_note}")
    for e in c.evidence:
        print(f'    cite: "{e.quote[:90]}" — {e.source_doc}')


async def main() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "FCX"
    force = "--force" in sys.argv

    rule(f"Generating macro report for {ticker}")
    t0 = time.time()
    report, diagnostics = await generate_report(ticker, force=force)
    print(f"done in {time.time() - t0:.1f}s")
    print(f"diagnostics: {diagnostics}")

    rule(f"HEADLINE — {report.ticker}")
    print(report.headline)

    rule(f"TAILWINDS ({len(report.tailwinds)})")
    for c in report.tailwinds:
        show_chain(c)

    rule(f"HEADWINDS ({len(report.headwinds)})")
    for c in report.headwinds:
        show_chain(c)

    rule("NET — SHORT RUN")
    print(report.net_short_run)
    rule("NET — LONG RUN")
    print(report.net_long_run)

    rule("THESIS BREAKERS")
    for i, b in enumerate(report.thesis_breakers, 1):
        print(f"  {i}. {b}")

    rule("CONFIDENCE NOTE")
    print(report.confidence_note)

    # ---------------------------------------------------------- acceptance
    rule("Acceptance check (spec 9.2 / 9.2b)")
    all_chains = report.tailwinds + report.headwinds
    multi_hop = [c for c in all_chains if len(c.path) >= 3]
    has_both = bool(report.tailwinds) and bool(report.headwinds)
    priced = [c for c in all_chains if re.search(r"[+-]?\d+(\.\d+)?%", c.priced_in_note)]
    trends = get_cached_trends(ticker)
    trends_ok = len(trends) >= 2 and all(len(t.sources) >= 2 for t in trends)
    non_us = [
        c for c in all_chains
        if any(n in NON_US_NODES or "_trend_" in n for n in c.path)
        and (set(c.path) & NON_US_NODES or _trend_non_us(c, trends, ticker))
    ]

    checks = {
        f"multi-hop chain (>=3 nodes): ({len(multi_hop)})": bool(multi_hop),
        f"both tailwinds and headwinds: ({len(report.tailwinds)}T/{len(report.headwinds)}H)": has_both,
        f"priced_in_note with real numbers: ({len(priced)}/{len(all_chains)})": bool(priced),
        f">=2 sector trends with >=2 sources: ({len(trends)})": trends_ok,
        f">=1 chain on a non-US condition: ({len(non_us)})": bool(non_us),
        "no buy/sell language": not re.search(
            r"\b(buy|sell|hold|overweight|underweight)\b",
            (report.headline + report.net_short_run + report.net_long_run).lower(),
        ),
    }
    failed = False
    for label, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
        failed = failed or not ok
    if failed:
        sys.exit(1)


def _trend_non_us(chain: Chain, trends, ticker: str) -> bool:
    from app.trends import trend_slug

    prefix = f"{ticker.lower()}_trend_"
    for node in chain.path:
        if node.startswith(prefix):
            slug = node[len(prefix):]
            for t in trends:
                if trend_slug(t) == slug and t.scope != "us":
                    return True
    return False


if __name__ == "__main__":
    asyncio.run(main())
