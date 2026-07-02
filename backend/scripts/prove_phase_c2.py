"""Phase C2 acceptance script (spec 9.2b, trend half).

Generates sector/global trend objects for FCX via web-grounded synthesis and
checks: >=2 trends, every trend has >=2 live source URLs, and at least one
trend covers a NON-US scope.

Run from backend/:  python scripts/prove_phase_c2.py [TICKER]
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cache import cache_get_json
from app.causal_graph import build_subgraph
from app.extraction.extractor import _profile_cache_key
from app.models import ExposureProfile
from app.trends import get_sector_trends, select_trend_exposures


def rule(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


async def main() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "FCX"
    force = "--force" in sys.argv

    cached = cache_get_json(_profile_cache_key(ticker), ttl=None)
    if cached is None:
        print(f"FAIL: no cached {ticker} profile — run scripts/prove_phase_b.py first")
        sys.exit(1)
    profile = ExposureProfile.model_validate(cached["profile"])

    picked = select_trend_exposures(profile)
    rule(f"Trend topics selected for {ticker} (cap 6, one per category)")
    for e in picked:
        print(f"  [{e.magnitude:11s}] {e.name}  ({e.category})")

    rule("Synthesizing trends (web-grounded, 2 LLM calls per topic)")
    t0 = time.time()
    trends = await get_sector_trends(profile, force=force)
    print(f"done in {time.time() - t0:.1f}s — {len(trends)} trends survived the >=2-sources rule")

    for t in trends:
        rule(f"{t.topic}  [{t.scope} | {t.direction}]")
        print(f"NOW:      {t.current_state}")
        print(f"HORIZON:  {t.horizon_note}")
        print(f"RELEVANCE: {t.relevance_to_company}")
        print("SOURCES:")
        for s in t.sources:
            print(f"  - {s[:110]}")

    rule("Graph integration")
    graph = build_subgraph(profile, trends=trends)
    trend_nodes = [n for n in graph.nodes if "_trend_" in n.id]
    trend_edges = [e for e in graph.edges if "_trend_" in e.source]
    print(f"subgraph now: {len(graph.nodes)} nodes / {len(graph.edges)} edges")
    for e in trend_edges:
        print(f"  {e.source}  ->  {e.target}  ({e.sign})")

    rule("Acceptance check (spec 9.2b, trend half)")
    ok_count = len(trends) >= 2
    ok_sources = all(len(t.sources) >= 2 for t in trends)
    ok_nonus = any(t.scope != "us" for t in trends)
    ok_graph = len(trend_nodes) == len(trends)
    print(f">=2 trends: {'PASS' if ok_count else 'FAIL'} ({len(trends)})")
    print(f"every trend has >=2 source URLs: {'PASS' if ok_sources else 'FAIL'}")
    print(f">=1 non-US scope: {'PASS' if ok_nonus else 'FAIL'} ({[t.scope for t in trends]})")
    print(f"trends appear as graph nodes: {'PASS' if ok_graph else 'FAIL'}")
    if not (ok_count and ok_sources and ok_nonus and ok_graph):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
