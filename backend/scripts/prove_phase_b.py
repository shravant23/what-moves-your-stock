"""Phase B acceptance script (spec 9.1).

Runs exposure extraction on FCX, verifies every citation against the actual
filing text, and asserts the profile has >=10 verified exposures.

Run from backend/:  python scripts/prove_phase_b.py [TICKER]
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.extraction.extractor import extract_exposure_profile


def rule(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


async def main() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "FCX"
    force = "--force" in sys.argv

    rule(f"Extracting exposure profile for {ticker}")
    t0 = time.time()
    profile, report = await extract_exposure_profile(ticker, force=force)
    print(f"done in {time.time() - t0:.1f}s")

    rule(f"{profile.company_name} ({profile.ticker})")
    print(profile.business_summary)

    print("\nRevenue segments:")
    for s in profile.revenue_segments:
        print(f"  - {s.name}: {s.approx_share}")

    print("\nGeographic mix:")
    for g in profile.geographic_mix:
        print(f"  - {g.region}: {g.approx_share}")

    d = profile.debt_profile
    print(f"\nDebt: {d.total_debt} | {d.fixed_vs_floating}")
    print(f"  rate sensitivity: {d.rate_sensitivity_note}")

    rule(f"Exposures ({len(profile.exposures)}) — all citation-verified")
    for e in profile.exposures:
        print(f"\n[{e.magnitude.upper():11s}] {e.name}  ({e.category}, {e.direction})")
        print(f"  {e.rationale}")
        for c in e.citations:
            print(f'  cite: "{c.quote}" — {c.source_doc} / {c.section}')

    rule("Citation verification report")
    print(f"citations checked : {report.citations_checked}")
    print(f"verified          : {report.citations_verified}")
    print(f"rejected          : {report.citations_rejected}")
    if report.rejected_quotes:
        for q in report.rejected_quotes:
            print(f'  rejected quote: "{q}"')
    if report.exposures_dropped:
        print(f"exposures dropped (no valid citation): {report.exposures_dropped}")

    rule("Acceptance check (spec 9.1)")
    n = len(profile.exposures)
    all_cited = all(len(e.citations) >= 1 for e in profile.exposures)
    print(f">=10 verified exposures: {'PASS' if n >= 10 else 'FAIL'} ({n})")
    print(f"every exposure has a verified quote: {'PASS' if all_cited else 'FAIL'}")
    if n < 10 or not all_cited:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
