"""Reasoning-engine guardrails: invalid chain paths are dropped and
unverifiable evidence is stripped in code, regardless of what the LLM says."""

from app.extraction.verify import Verifier
from app.models import Chain, Graph, GraphEdge, GraphNode, LLMMacroReport
from app.reasoning import _validate_chains, select_proxies

from .conftest import make_citation

DOCS = {"TST 10-K FY2025": "We mine copper in Indonesia."}


def _graph() -> Graph:
    mk = lambda s, t: GraphEdge(  # noqa: E731
        source=s, target=t, sign="positive", lag="x", confidence="high",
        rationale="r", source_note="s",
    )
    return Graph(
        nodes=[
            GraphNode(id="china_growth", label="China growth", category="region"),
            GraphNode(id="copper_price", label="Copper price", category="commodity"),
            GraphNode(id="tst", label="Test Co", category="company"),
        ],
        edges=[mk("china_growth", "copper_price"), mk("copper_price", "tst")],
    )


def _chain(path: list[str], quote: str = "We mine copper in Indonesia") -> Chain:
    return Chain(
        path=path,
        direction="tailwind",
        horizon="both",
        strength="strong",
        explanation="Explanation.",
        evidence=[make_citation(quote)],
        priced_in_note="CPER +10% over 6 months.",
    )


def _report(tailwinds: list[Chain], headwinds: list[Chain] | None = None) -> LLMMacroReport:
    return LLMMacroReport(
        headline="Neutral sentence.",
        tailwinds=tailwinds,
        headwinds=headwinds or [_chain(["copper_price", "tst"])],
        net_short_run="Both sides weighed.",
        net_long_run="Both sides weighed.",
        thesis_breakers=["Copper below $9,000/t for two quarters."],
        confidence_note="Least sure about X.",
    )


def test_valid_chain_survives():
    report = _report([_chain(["china_growth", "copper_price", "tst"])])
    cleaned, diag = _validate_chains(report, _graph(), "tst", Verifier(DOCS))
    assert len(cleaned.tailwinds) == 1
    assert diag["chains_dropped"] == []


def test_hallucinated_path_is_dropped():
    # china_growth -> tst is not an edge in the graph
    report = _report([_chain(["china_growth", "tst"])])
    cleaned, diag = _validate_chains(report, _graph(), "tst", Verifier(DOCS))
    assert cleaned.tailwinds == []
    assert diag["chains_dropped"] == ["china_growth -> tst"]


def test_chain_not_ending_at_company_is_dropped():
    report = _report([_chain(["china_growth", "copper_price"])])
    cleaned, _ = _validate_chains(report, _graph(), "tst", Verifier(DOCS))
    assert cleaned.tailwinds == []


def test_unverifiable_evidence_is_stripped_but_chain_kept():
    report = _report([_chain(["copper_price", "tst"], quote="a fabricated quote")])
    cleaned, diag = _validate_chains(report, _graph(), "tst", Verifier(DOCS))
    assert len(cleaned.tailwinds) == 1
    assert cleaned.tailwinds[0].evidence == []
    assert diag["citations_rejected"] == 1


def test_select_proxies_maps_and_caps():
    mk = lambda s: GraphEdge(  # noqa: E731
        source=s, target="tst", sign="positive", lag="x", confidence="high",
        rationale="r", source_note="s",
    )
    graph = Graph(
        nodes=[GraphNode(id="tst", label="T", category="company")],
        edges=[mk(s) for s in [
            "copper_price", "gold_price", "china_growth", "oil_price", "banks", "us_housing",
        ]],
    )
    proxies = select_proxies(graph, "tst")
    assert proxies[0] == "CPER"
    assert "GLD" in proxies and "FXI" in proxies
    assert len(proxies) <= 4
