"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import NetworkGraph from "@/components/NetworkGraph";
import NodeDrawer from "@/components/NodeDrawer";
import { api, Graph, GraphEdge, GraphNode } from "@/lib/api";

export default function GraphExplorer() {
  const [graph, setGraph] = useState<Graph | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<{ node: GraphNode; edges: GraphEdge[] } | null>(null);

  useEffect(() => {
    api
      .fullGraph()
      .then(setGraph)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load graph."));
  }, []);

  const labelOf = useMemo(() => {
    const map = new Map(graph?.nodes.map((n) => [n.id, n.label]) ?? []);
    return (id: string) => map.get(id) ?? id;
  }, [graph]);

  return (
    <main className="flex h-screen flex-col">
      <header className="flex items-center gap-4 border-b border-line px-5 py-3">
        <Link href="/" className="flex items-center gap-2 text-slate-100 transition hover:text-accent">
          <svg width="18" height="18" viewBox="0 0 32 32" aria-hidden>
            <path d="M16 6 L27 24 L5 24 Z" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" />
          </svg>
          <span className="text-sm font-semibold">Prism</span>
        </Link>
        <span className="text-slate-600">/</span>
        <span className="text-sm font-medium text-slate-300">Macro causal graph</span>
        <span className="ml-auto hidden text-xs text-slate-500 sm:block">
          {graph ? `${graph.nodes.length} nodes · ${graph.edges.length} edges` : ""}
        </span>
      </header>

      <div className="relative flex-1">
        {error && (
          <div className="flex h-full items-center justify-center">
            <div className="panel max-w-md p-8 text-center">
              <div className="mb-2 text-sm font-semibold text-neg">Couldn&apos;t load the graph</div>
              <p className="text-xs text-slate-400">
                {error} — is the backend running on port 8000?
              </p>
            </div>
          </div>
        )}
        {!error && !graph && (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">
            Loading the causal graph…
          </div>
        )}
        {graph && (
          <>
            <NetworkGraph
              graph={graph}
              onSelectNode={(node, edges) =>
                setSelected(node ? { node, edges } : null)
              }
            />
            {selected && (
              <NodeDrawer
                node={selected.node}
                edges={selected.edges}
                labelOf={labelOf}
                onClose={() => setSelected(null)}
              />
            )}
          </>
        )}
      </div>

      <footer className="border-t border-line/60 py-2 text-center text-[10px] text-slate-600">
        ~120 hand-curated, economically conventional macro linkages · Prism is a research tool, not investment advice.
      </footer>
    </main>
  );
}
