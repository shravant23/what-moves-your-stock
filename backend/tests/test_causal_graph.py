"""Seed graph integrity + subgraph wiring (spec section 5)."""

from app.causal_graph import build_subgraph, find_chains, load_seed, match_exposure
from app.models import GraphEdge, GraphNode

from .conftest import make_exposure, make_profile, make_trend

# ------------------------------------------------------------- seed graph


def test_seed_graph_size_and_integrity():
    nodes, edges = load_seed()
    assert len(edges) >= 110, "spec asks for ~120 seed edges"
    ids = {n.id for n in nodes}
    for e in edges:
        assert e.source in ids and e.target in ids


def test_seed_has_no_duplicate_node_ids_or_edges():
    nodes, edges = load_seed()
    ids = [n.id for n in nodes]
    assert len(ids) == len(set(ids))
    pairs = [(e.source, e.target) for e in edges]
    assert len(pairs) == len(set(pairs))


# ------------------------------------------------------- exposure matching


def test_match_exposure_by_alias():
    seed_nodes, _ = load_seed()
    assert match_exposure(make_exposure(name="Copper Prices"), seed_nodes) == "copper_price"
    assert match_exposure(make_exposure(name="U.S. Tariffs and Trade Policies"), seed_nodes) == "us_tariffs"


def test_unmatched_exposure_returns_none():
    seed_nodes, _ = load_seed()
    assert match_exposure(make_exposure(name="Quantum Flux Capacitance"), seed_nodes) is None


# ------------------------------------------------------------- subgraph


def test_subgraph_has_company_node_and_exposure_edges():
    profile = make_profile([make_exposure(name="Copper Prices")])
    graph = build_subgraph(profile)
    ids = {n.id for n in graph.nodes}
    assert "tst" in ids
    assert "copper_price" in ids
    edge = next(e for e in graph.edges if e.target == "tst")
    assert edge.source == "copper_price"
    assert edge.sign == "positive"  # benefits_when_up


def test_hurt_when_up_exposure_gets_negative_edge():
    profile = make_profile([make_exposure(name="Copper Prices", direction="hurt_when_up")])
    graph = build_subgraph(profile)
    edge = next(e for e in graph.edges if e.target == "tst")
    assert edge.sign == "negative"


def test_mixed_exposure_flagged_in_rationale():
    profile = make_profile([make_exposure(name="Copper Prices", direction="mixed")])
    graph = build_subgraph(profile)
    edge = next(e for e in graph.edges if e.target == "tst")
    assert "(mixed effect)" in edge.rationale


def test_unmatched_exposure_becomes_standalone_node():
    profile = make_profile([make_exposure(name="Quantum Flux Capacitance", category="demand_driver")])
    graph = build_subgraph(profile)
    standalone = [n for n in graph.nodes if n.id.startswith("tst_")]
    assert len(standalone) == 1
    assert standalone[0].label == "Quantum Flux Capacitance"


def test_upstream_context_enables_multi_hop_chains():
    profile = make_profile([make_exposure(name="Copper Prices")])
    graph = build_subgraph(profile)
    chains = find_chains(graph, "tst")
    assert any(len(c) >= 3 for c in chains), "expected macro -> copper_price -> company paths"


# ------------------------------------------------------------- trend nodes


def test_accelerating_harmful_trend_is_negative_into_company():
    exposure = make_exposure(
        name="Water Supply Availability", category="demand_driver", direction="hurt_when_up"
    )
    trend = make_trend(
        topic="Global water scarcity xyzzy",  # no seed alias match -> wired to company
        direction="accelerating",
        source_exposure="Water Supply Availability",
    )
    graph = build_subgraph(make_profile([exposure]), trends=[trend])
    trend_edge = next(e for e in graph.edges if "_trend_" in e.source)
    assert trend_edge.target == "tst"
    assert trend_edge.sign == "negative"  # accelerating x hurt_when_up = headwind


def test_trend_matching_a_driver_wires_to_that_driver():
    exposure = make_exposure(name="Copper Prices")
    trend = make_trend(topic="Copper price outlook", direction="accelerating")
    graph = build_subgraph(make_profile([exposure]), trends=[trend])
    trend_edge = next(e for e in graph.edges if "_trend_" in e.source)
    assert trend_edge.target == "copper_price"
    assert trend_edge.sign == "positive"


def test_trend_nodes_labeled_live():
    graph = build_subgraph(make_profile(), trends=[make_trend()])
    trend_node = next(n for n in graph.nodes if "_trend_" in n.id)
    assert trend_node.label.endswith("· live")


# ------------------------------------------------------------- find_chains


def test_find_chains_respects_max_length_and_endpoint():
    nodes = [GraphNode(id=i, label=i, category="sector") for i in ["a", "b", "c", "d", "co"]]
    mk = lambda s, t: GraphEdge(  # noqa: E731
        source=s, target=t, sign="positive", lag="x", confidence="high",
        rationale="r", source_note="s",
    )
    from app.models import Graph

    graph = Graph(nodes=nodes, edges=[mk("a", "b"), mk("b", "c"), mk("c", "co"), mk("d", "a")])
    chains = find_chains(graph, "co", max_len=3)
    assert all(c[-1] == "co" for c in chains)
    assert ["b", "c", "co"] in chains
    assert ["a", "b", "c", "co"] in chains
    assert not any(len(c) > 4 for c in chains)
