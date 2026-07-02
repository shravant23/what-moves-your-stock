"""Phase C acceptance script.

Validates the seed causal graph (size + referential integrity), persists it
to SQLite, builds the FCX subgraph from the cached exposure profile, and
prints example multi-hop chains ending at the company node.

Run from backend/:  python scripts/prove_phase_c.py
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cache import cache_get_json
from app.causal_graph import build_subgraph, load_seed, persist_seed
from app.extraction.extractor import _profile_cache_key
from app.models import ExposureProfile


def rule(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def find_chains(edges, company_id: str, max_len: int = 3) -> list[list[str]]:
    """All simple paths of length 2..max_len ending at the company node."""
    incoming: dict[str, list[str]] = {}
    for e in edges:
        incoming.setdefault(e.target, []).append(e.source)

    chains: list[list[str]] = []

    def walk(path: list[str]) -> None:
        head = path[0]
        if len(path) >= 3:
            chains.append(path)
        if len(path) > max_len:
            return
        for src in incoming.get(head, []):
            if src not in path:
                walk([src, *path])

    walk([company_id])
    return chains


def main() -> None:
    rule("Seed graph")
    nodes, edges = load_seed()  # raises on referential integrity failure
    print(f"nodes: {len(nodes)}   edges: {len(edges)}")
    print("node categories:", dict(Counter(n.category for n in nodes)))
    print("edge confidence:", dict(Counter(e.confidence for e in edges)))
    persist_seed()
    print("persisted to SQLite: OK")

    rule("FCX subgraph (from cached exposure profile)")
    cached = cache_get_json(_profile_cache_key("FCX"), ttl=None)
    if cached is None:
        print("FAIL: no cached FCX profile — run scripts/prove_phase_b.py first")
        sys.exit(1)
    profile = ExposureProfile.model_validate(cached["profile"])
    graph = build_subgraph(profile)

    company_edges = [e for e in graph.edges if e.target == "fcx"]
    matched = [e.source for e in company_edges if not e.source.startswith("fcx_")]
    standalone = [e.source for e in company_edges if e.source.startswith("fcx_")]
    print(f"subgraph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    print(f"exposures wired to company: {len(company_edges)} "
          f"({len(matched)} matched to seed nodes, {len(standalone)} standalone)")
    print("matched seed nodes:", matched)
    print("standalone nodes:", standalone)

    chains = find_chains(graph.edges, "fcx")
    multi_hop = [c for c in chains if len(c) >= 4]
    print(f"\nchains ending at FCX: {len(chains)} (length>=3: {len(multi_hop)})")
    print("sample multi-hop chains:")
    for c in multi_hop[:8]:
        print("   " + " -> ".join(c))

    rule("Acceptance check")
    ok_size = len(edges) >= 110
    ok_wiring = len(company_edges) >= 10
    ok_multihop = len(multi_hop) >= 1
    print(f"seed graph ~120 edges: {'PASS' if ok_size else 'FAIL'} ({len(edges)})")
    print(f">=10 exposures wired into subgraph: {'PASS' if ok_wiring else 'FAIL'} ({len(company_edges)})")
    print(f"multi-hop chains (len>=3) exist: {'PASS' if ok_multihop else 'FAIL'} ({len(multi_hop)})")
    if not (ok_size and ok_wiring and ok_multihop):
        sys.exit(1)


if __name__ == "__main__":
    main()
