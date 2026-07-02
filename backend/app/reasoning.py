"""The Reasoning Engine (spec section 6).

One orchestrated LLM pass receives: the ExposureProfile, current macro state
(FRED + World Bank), SectorTrends, candidate graph chains (paths <=3 ending
at the company), and trailing price action for the ticker + mapped proxies.

Structural guarantees enforced in code, not prompt-hope:
  - candidate chains are enumerated from the actual subgraph; any chain the
    model returns whose path is not a valid edge-walk is dropped
  - evidence citations are re-verified against filing text (Phase B verifier)
  - temperature 0.3, schema-validated output with one retry
"""

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from .cache import cache_get_json, cache_set_json
from .causal_graph import build_subgraph, find_chains
from .clients import fred, market, worldbank
from .extraction.extractor import extract_exposure_profile
from .extraction.verify import Verifier
from .llm import call_structured
from .models import (
    Chain,
    ExposureProfile,
    Graph,
    LLMMacroReport,
    MacroReport,
    SectorTrend,
)
from .trends import get_sector_trends

REPORT_TTL = timedelta(hours=24)

# seed node id -> most liquid ETF proxy (spec section 3 universe)
PROXY_MAP: dict[str, str] = {
    "copper_price": "CPER",
    "gold_price": "GLD",
    "silver_price": "SLV",
    "oil_price": "USO",
    "natural_gas_price": "USO",
    "jet_fuel_price": "USO",
    "china_growth": "FXI",
    "china_property": "FXI",
    "europe_growth": "EWG",
    "japan_growth": "EWJ",
    "em_growth": "EEM",
    "semiconductors": "XLK",
    "semiconductor_demand": "XLK",
    "ai_capex": "XLK",
    "banks": "XLF",
    "us_housing": "XLRE",
    "homebuilders": "XLRE",
    "reits": "XLRE",
    "utilities": "XLU",
    "consumer_discretionary": "XLY",
    "retailers": "XLY",
    "home_improvement": "XLY",
    "consumer_staples_demand": "XLP",
    "metals_miners": "XLB",
    "chemicals": "XLB",
    "steel_price": "XLB",
    "aluminum_price": "XLB",
    "energy_producers": "XLE",
    "airlines": "XLI",
    "travel_demand": "XLI",
    "transports": "XLI",
    "global_ip": "XLI",
}

SYSTEM_PROMPT = """You are a macro research analyst writing a cited, traceable report on how \
macroeconomic forces flow through to one company. You are rigorous and neutral.

Hard rules:
1. ARGUE BOTH DIRECTIONS. Produce 2-5 tailwind chains AND 2-5 headwind chains before \
concluding. The net_short_run and net_long_run assessments must explicitly weigh both sides.
2. Every chain's `path` must be copied EXACTLY from the CANDIDATE CHAINS list provided \
(a list of node ids ending at the company). Do not invent paths or node ids.
3. Every chain's `evidence` must copy citations VERBATIM (source_doc, section, quote) from \
the exposure profile citations provided. Do not invent or alter quotes.
4. Every `priced_in_note` must reference specific numbers from the PRICE ACTION data \
(e.g. "copper proxy CPER +18% over 6 months suggests much of this is reflected").
5. Use the SECTOR TRENDS and non-US conditions (China, Indonesia, Latin America, Europe) \
where relevant — at least one chain should rest on a non-US condition when the company has \
international exposure. Prefer chains through trend nodes when a trend directly bears on them.
6. thesis_breakers: 3-5 concrete, observable falsifiers with thresholds where possible \
("China property starts fall another 20%", "copper below $9,000/t for two quarters").
7. NEVER give investment advice. No buy/sell/hold/overweight language anywhere. The headline \
is one neutral, factual sentence.
8. Plain English throughout — a smart non-finance reader should follow every sentence."""


def _report_cache_key(ticker: str) -> str:
    return f"report:{ticker.upper()}"


def select_proxies(graph: Graph, company_id: str, cap: int = 4) -> list[str]:
    """2-4 ETF proxies for the company's most important wired exposures."""
    proxies: list[str] = []
    for e in graph.edges:
        if e.target == company_id and e.source in PROXY_MAP:
            symbol = PROXY_MAP[e.source]
            if symbol not in proxies:
                proxies.append(symbol)
        if len(proxies) >= cap:
            break
    return proxies


def _format_inputs(
    profile: ExposureProfile,
    graph: Graph,
    chains: list[list[str]],
    macro: list[fred.SeriesSummary],
    geo: list[dict],
    trends: list[SectorTrend],
    prices: dict[str, market.PriceSummary],
) -> str:
    parts: list[str] = []
    company_id = profile.ticker.lower()
    parts.append(
        f"COMPANY: {profile.company_name} ({profile.ticker}) — graph node id: {company_id}\n"
        f"{profile.business_summary}\n"
        f"As of: {datetime.now(timezone.utc).date().isoformat()}"
    )

    parts.append("\n== EXPOSURE PROFILE (citations are verified verbatim quotes) ==")
    for e in profile.exposures:
        parts.append(f"- {e.name} [{e.category} | {e.direction} | {e.magnitude}]: {e.rationale}")
        for c in e.citations:
            parts.append(f'    citation: source_doc="{c.source_doc}" section="{c.section}" quote="{c.quote}"')

    parts.append("\n== CURRENT MACRO STATE (latest value, 12-month change) ==")
    for s in macro:
        if s.latest_value is None:
            continue
        parts.append(
            f"- {s.name} ({s.series_id}): {s.latest_value} as of {s.latest_date}, "
            f"12m change {s.change_1y:+} ({s.pct_change_1y:+}% y/y)"
            if s.pct_change_1y is not None
            else f"- {s.name} ({s.series_id}): {s.latest_value} as of {s.latest_date}"
        )

    if geo:
        parts.append("\n== COUNTRY DATA (World Bank, annual) ==")
        for g in geo:
            gdp = g.get("Real GDP growth (annual %)")
            infl = g.get("Inflation, CPI (annual %)")
            line = f"- {g.get('country', g['code'])}:"
            if gdp:
                line += f" GDP growth {gdp['value']}% ({gdp['year']})"
            if infl:
                line += f", inflation {infl['value']}% ({infl['year']})"
            parts.append(line)

    parts.append("\n== SECTOR TRENDS (web-sourced, current) ==")
    for t in trends:
        parts.append(
            f"- {t.topic} [scope={t.scope}, direction={t.direction}]\n"
            f"    now: {t.current_state}\n"
            f"    horizon: {t.horizon_note}\n"
            f"    relevance: {t.relevance_to_company}"
        )

    parts.append("\n== PRICE ACTION (trailing % changes) ==")
    for symbol, p in prices.items():
        if p.last_close is None:
            continue
        parts.append(
            f"- {symbol}: last {p.last_close} ({p.as_of}), "
            f"1m {p.pct_1m:+}%, 6m {p.pct_6m:+}%, 1y {p.pct_1y:+}%"
        )

    node_labels = {n.id: n.label for n in graph.nodes}
    parts.append(
        "\n== CANDIDATE CHAINS (copy `path` exactly from these; format: ids | labels) =="
    )
    for chain in chains:
        labels = " -> ".join(node_labels.get(n, n) for n in chain)
        parts.append(f"- {chain} | {labels}")

    parts.append(
        "\nProduce the macro report now. Remember: both directions, verbatim citations, "
        "price-anchored priced_in_notes, and at least one chain resting on a non-US condition."
    )
    return "\n".join(parts)


def _validate_chains(
    report: LLMMacroReport, graph: Graph, company_id: str, verifier: Verifier
) -> tuple[LLMMacroReport, dict]:
    """Drop chains whose path isn't a real edge-walk ending at the company;
    strip evidence citations that fail string verification."""
    edge_set = {(e.source, e.target) for e in graph.edges}
    diagnostics = {"chains_dropped": [], "citations_rejected": 0}

    def clean(chains: list[Chain]) -> list[Chain]:
        kept = []
        for chain in chains:
            path_ok = (
                len(chain.path) >= 2
                and chain.path[-1] == company_id
                and all((a, b) in edge_set for a, b in zip(chain.path, chain.path[1:]))
            )
            if not path_ok:
                diagnostics["chains_dropped"].append(" -> ".join(chain.path))
                continue
            verified = [c for c in chain.evidence if verifier.citation_ok(c)]
            diagnostics["citations_rejected"] += len(chain.evidence) - len(verified)
            kept.append(chain.model_copy(update={"evidence": verified}))
        return kept

    cleaned = report.model_copy(
        update={"tailwinds": clean(report.tailwinds), "headwinds": clean(report.headwinds)}
    )
    return cleaned, diagnostics


async def generate_report(
    ticker: str, force: bool = False, progress=None
) -> tuple[MacroReport, dict]:
    """Full analysis: profile -> trends -> graph -> macro/prices -> reasoning.
    `progress` is an optional callback(stage_name) for job status reporting."""

    def report_stage(stage: str) -> None:
        if progress is not None:
            progress(stage)

    key = _report_cache_key(ticker)
    if not force:
        cached = cache_get_json(key, REPORT_TTL)
        if cached is not None:
            return MacroReport.model_validate(cached["report"]), cached["diagnostics"]

    report_stage("fetching_filings")
    profile, _ = await extract_exposure_profile(ticker, progress=progress)

    report_stage("synthesizing_trends")
    trends = await get_sector_trends(profile)
    graph = build_subgraph(profile, trends=trends)
    company_id = profile.ticker.lower()

    report_stage("pulling_macro")
    async with httpx.AsyncClient(follow_redirects=True) as client:
        macro = await fred.get_macro_snapshot(client)
        geo = await worldbank.get_geo_snapshots(
            client, [g.region for g in profile.geographic_mix]
        )

    proxies = select_proxies(graph, company_id)
    symbols = [profile.ticker, *proxies]
    prices = {
        s: await asyncio.to_thread(market.get_price_summary, s) for s in symbols
    }

    report_stage("tracing_chains")
    chains = find_chains(graph, company_id)

    report_stage("writing_report")
    user_content = _format_inputs(profile, graph, chains, macro, geo, trends, prices)
    llm_report: LLMMacroReport = await asyncio.to_thread(
        call_structured, SYSTEM_PROMPT, user_content, LLMMacroReport, 0.3, 16000
    )

    # Re-verify citations against the actual filing texts (same docs as Phase B).
    from .extraction.extractor import _gather_documents

    async with httpx.AsyncClient(follow_redirects=True) as client:
        _, full_texts, _ = await _gather_documents(client, ticker)
    cleaned, diagnostics = _validate_chains(
        llm_report, graph, company_id, Verifier(full_texts)
    )

    report = MacroReport(
        ticker=profile.ticker,
        generated_at=datetime.now(timezone.utc),
        **cleaned.model_dump(),
    )
    cache_set_json(
        key,
        {"report": report.model_dump(mode="json"), "diagnostics": diagnostics},
    )
    return report, diagnostics
