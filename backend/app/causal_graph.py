"""Causal graph service (spec section 5).

The seed graph (~120 hand-written, economically conventional edges) is loaded
from data/seed_graph.json at startup and persisted to SQLite. When a ticker
is analyzed, the company becomes a node: each verified exposure is matched to
a seed macro node via alias keywords (or becomes a standalone node), and an
edge is drawn into the company. The subgraph served to the frontend includes
upstream seed edges to depth 2, so paths of length <=3 end at the company."""

import json
import re
from functools import lru_cache

from sqlmodel import Field, SQLModel, select

from .config import BACKEND_DIR
from .db import engine, get_session
from .models import (
    Exposure,
    ExposureProfile,
    Graph,
    GraphEdge,
    GraphNode,
    SectorTrend,
    SeedNode,
)
from .trends import trend_slug

SEED_PATH = BACKEND_DIR / "data" / "seed_graph.json"

# exposure.category -> node category for standalone (unmatched) exposure nodes
_CATEGORY_MAP = {
    "commodity_input": "commodity",
    "commodity_output": "commodity",
    "geography": "region",
    "interest_rates": "rate",
    "currency": "currency",
    "regulation": "policy",
    "demand_driver": "demand_driver",
    "customer_concentration": "demand_driver",
    "supplier_concentration": "demand_driver",
}

# exposure.magnitude -> edge confidence (drives edge width in the UI)
_MAGNITUDE_CONFIDENCE = {
    "critical": "high",
    "significant": "high",
    "moderate": "medium",
    "minor": "low",
}


class GraphNodeRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    label: str
    category: str
    origin: str = Field(default="seed", index=True)  # "seed" or a ticker


class GraphEdgeRow(SQLModel, table=True):
    pk: int | None = Field(default=None, primary_key=True)
    source: str
    target: str
    sign: str
    lag: str
    confidence: str
    rationale: str
    source_note: str
    origin: str = Field(default="seed", index=True)


@lru_cache(maxsize=1)
def load_seed() -> tuple[list[SeedNode], list[GraphEdge]]:
    raw = json.loads(SEED_PATH.read_text())
    nodes = [SeedNode.model_validate(n) for n in raw["nodes"]]
    edges = [GraphEdge.model_validate(e) for e in raw["edges"]]
    ids = {n.id for n in nodes}
    for e in edges:
        if e.source not in ids or e.target not in ids:
            raise ValueError(f"Seed edge references unknown node: {e.source} -> {e.target}")
    return nodes, edges


def persist_seed() -> None:
    """Idempotently (re)write the seed graph into SQLite."""
    SQLModel.metadata.create_all(engine)
    nodes, edges = load_seed()
    with get_session() as session:
        for row in session.exec(select(GraphNodeRow).where(GraphNodeRow.origin == "seed")):
            session.delete(row)
        for row in session.exec(select(GraphEdgeRow).where(GraphEdgeRow.origin == "seed")):
            session.delete(row)
        for n in nodes:
            session.add(GraphNodeRow(id=n.id, label=n.label, category=n.category))
        for e in edges:
            session.add(GraphEdgeRow(**e.model_dump()))
        session.commit()


def get_full_graph() -> Graph:
    nodes, edges = load_seed()
    return Graph(nodes=[GraphNode(**n.model_dump(exclude={"aliases"})) for n in nodes], edges=edges)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def match_exposure(exposure: Exposure, seed_nodes: list[SeedNode]) -> str | None:
    """Match an exposure to a seed node by alias keywords. Longest matching
    alias wins (specificity); returns None if nothing matches."""
    name = f" {exposure.name.lower()} "
    best_id, best_len = None, 0
    for node in seed_nodes:
        for candidate in [node.label.lower(), *[a.lower() for a in node.aliases]]:
            if candidate and candidate in name and len(candidate) > best_len:
                best_id, best_len = node.id, len(candidate)
    return best_id


def _exposure_edge(node_id: str, company_id: str, exposure: Exposure, ticker: str) -> GraphEdge:
    if exposure.direction == "benefits_when_up":
        sign, rationale = "positive", exposure.rationale
    elif exposure.direction == "hurt_when_up":
        sign, rationale = "negative", exposure.rationale
    else:  # mixed — the edge sign vocabulary is binary; flag it in the rationale
        sign, rationale = "negative", f"(mixed effect) {exposure.rationale}"
    return GraphEdge(
        source=node_id,
        target=company_id,
        sign=sign,
        lag="0-1 quarters",
        confidence=_MAGNITUDE_CONFIDENCE[exposure.magnitude],
        rationale=rationale,
        source_note=f"{ticker.upper()} filings (citation-verified)",
    )


def _match_text(text: str, seed_nodes: list[SeedNode]) -> str | None:
    """Alias-match arbitrary text (e.g. a trend topic) to a seed node."""
    haystack = f" {text.lower()} "
    best_id, best_len = None, 0
    for node in seed_nodes:
        for candidate in [node.label.lower(), *[a.lower() for a in node.aliases]]:
            if candidate and candidate in haystack and len(candidate) > best_len:
                best_id, best_len = node.id, len(candidate)
    return best_id


def build_subgraph(
    profile: ExposureProfile, trends: list[SectorTrend] | None = None
) -> Graph:
    """Company node + exposure nodes/edges + upstream seed context (depth 2),
    so every macro->...->company path has length <= 3. Sector trends (5b)
    join as demand_driver nodes wired into the matching macro node."""
    seed_nodes, seed_edges = load_seed()
    seed_by_id = {n.id: n for n in seed_nodes}
    ticker = profile.ticker
    company_id = ticker.lower()

    nodes: dict[str, GraphNode] = {
        company_id: GraphNode(id=company_id, label=profile.company_name.title(), category="company")
    }
    edges: list[GraphEdge] = []
    matched_ids: set[str] = set()

    for exposure in profile.exposures:
        node_id = match_exposure(exposure, seed_nodes)
        if node_id is not None:
            seed_node = seed_by_id[node_id]
            nodes[node_id] = GraphNode(**seed_node.model_dump(exclude={"aliases"}))
            matched_ids.add(node_id)
        else:
            node_id = f"{company_id}_{_slug(exposure.name)}"
            nodes[node_id] = GraphNode(
                id=node_id,
                label=exposure.name,
                category=_CATEGORY_MAP[exposure.category],
            )
        edges.append(_exposure_edge(node_id, company_id, exposure, ticker))

    # Upstream expansion: seed edges into matched nodes (depth 1), then edges
    # into those sources (depth 2). Also captures edges among matched nodes.
    # Sector trends become nodes connected to the matching macro node when
    # one exists (trend -> driver -> company), otherwise straight to company.
    exposure_direction = {e.name: e.direction for e in profile.exposures}
    for trend in trends or []:
        trend_id = f"{company_id}_trend_{trend_slug(trend)}"
        nodes[trend_id] = GraphNode(id=trend_id, label=trend.topic, category="demand_driver")
        target = _match_text(trend.topic, seed_nodes)
        if target is None or target not in nodes:
            target = company_id
        # Into a driver node: sign = is the driver strengthening or weakening.
        # Into the company: combine with how the underlying exposure cuts —
        # an accelerating harmful trend is a headwind (negative), etc.
        rising = trend.direction in ("accelerating", "stable")
        if target == company_id:
            direction = exposure_direction.get(trend.source_exposure or "", "mixed")
            helps_when_rising = direction == "benefits_when_up"
            sign = "positive" if rising == helps_when_rising else "negative"
        else:
            sign = "positive" if rising else "negative"
        edges.append(
            GraphEdge(
                source=trend_id,
                target=target,
                sign=sign,
                lag="current",
                confidence="medium",
                rationale=f"[{trend.direction}] {trend.relevance_to_company}",
                source_note=f"Web-sourced trend, as of {trend.as_of.date().isoformat()}",
            )
        )

    frontier = set(matched_ids)
    for _ in range(2):
        new_frontier: set[str] = set()
        for e in seed_edges:
            if e.target in frontier:
                if e.source not in nodes:
                    new_frontier.add(e.source)
                    src = seed_by_id[e.source]
                    nodes[e.source] = GraphNode(**src.model_dump(exclude={"aliases"}))
                if not any(x.source == e.source and x.target == e.target for x in edges):
                    edges.append(e)
        frontier = new_frontier
        if not frontier:
            break

    return Graph(nodes=list(nodes.values()), edges=edges)


def find_chains(graph: Graph, company_id: str, max_len: int = 3) -> list[list[str]]:
    """All simple paths of length 2..max_len (in edges) ending at the company
    node. These are the candidate causal chains the reasoning engine may cite."""
    incoming: dict[str, list[str]] = {}
    for e in graph.edges:
        incoming.setdefault(e.target, []).append(e.source)

    chains: list[list[str]] = []

    def walk(path: list[str]) -> None:
        head = path[0]
        if len(path) >= 2:
            chains.append(path)
        if len(path) > max_len:
            return
        for src in incoming.get(head, []):
            if src not in path:
                walk([src, *path])

    walk([company_id])
    return chains


def persist_subgraph(profile: ExposureProfile) -> Graph:
    """Build the ticker subgraph and store its ticker-derived rows in SQLite
    (idempotent — prior rows for the ticker are replaced)."""
    graph = build_subgraph(profile)
    origin = profile.ticker.upper()
    seed_ids = {n.id for n in load_seed()[0]}
    with get_session() as session:
        for row in session.exec(select(GraphNodeRow).where(GraphNodeRow.origin == origin)):
            session.delete(row)
        for row in session.exec(select(GraphEdgeRow).where(GraphEdgeRow.origin == origin)):
            session.delete(row)
        for n in graph.nodes:
            if n.id not in seed_ids:
                session.add(GraphNodeRow(id=n.id, label=n.label, category=n.category, origin=origin))
        for e in graph.edges:
            if e.source_note.startswith(origin):
                session.add(GraphEdgeRow(**e.model_dump(), origin=origin))
        session.commit()
    return graph
