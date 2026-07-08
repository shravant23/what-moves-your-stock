"""Build backend/data/demo_cache.db — the tiny cache bundled with public
demo deployments. Includes only what serving needs (profiles, reports,
trend aggregates) for tickers whose analysis completed; filings and raw
market data are left out.

Run from backend/ after analyzing the tickers you want in the demo:
    python scripts/make_demo_cache.py
"""

import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SRC = BACKEND / "prism.db"
DST = BACKEND / "data" / "demo_cache.db"


def main() -> None:
    if not SRC.exists():
        sys.exit(f"{SRC} not found — analyze some tickers first")

    src = sqlite3.connect(SRC)
    tickers = [
        row[0].removeprefix("report:")
        for row in src.execute("SELECT key FROM cacheentry WHERE key LIKE 'report:%'")
    ]
    if not tickers:
        sys.exit("no completed reports in the cache — nothing to bundle")

    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.unlink(missing_ok=True)
    dst = sqlite3.connect(DST)
    dst.execute(
        "CREATE TABLE cacheentry (key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL, "
        "fetched_at DATETIME NOT NULL)"
    )

    copied = 0
    for t in tickers:
        for key in (f"profile:{t}", f"report:{t}", f"trends:{t}"):
            row = src.execute(
                "SELECT key, value, fetched_at FROM cacheentry WHERE key = ?", (key,)
            ).fetchone()
            if row:
                dst.execute("INSERT INTO cacheentry VALUES (?, ?, ?)", row)
                copied += 1
    dst.commit()

    size_kb = DST.stat().st_size / 1024
    print(f"demo cache: {len(tickers)} tickers ({', '.join(sorted(tickers))}), "
          f"{copied} entries, {size_kb:.0f} KB -> {DST}")


if __name__ == "__main__":
    main()
