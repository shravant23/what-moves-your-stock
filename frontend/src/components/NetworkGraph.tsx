"use client";

import { forceCollide } from "d3-force";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
// Imported statically so the ref actually attaches (next/dynamic does not
// forward refs). This module itself is dynamically imported by the pages
// with ssr:false, so window-dependent code never runs on the server.
import ForceGraph2D from "react-force-graph-2d";
import {
  CATEGORY_COLORS,
  CATEGORY_LABELS,
  Graph,
  GraphEdge,
  GraphNode,
  NodeCategory,
} from "@/lib/api";

interface FGNode extends GraphNode {
  x?: number;
  y?: number;
}
interface FGLink extends Omit<GraphEdge, "source" | "target"> {
  source: FGNode | string;
  target: FGNode | string;
  key: string;
}

const CONFIDENCE_WIDTH = { high: 2.2, medium: 1.3, low: 0.7 } as const;
const BG = "#0A0E1A";

function endpointId(v: FGNode | string): string {
  return typeof v === "string" ? v : v.id;
}

export default function NetworkGraph({
  graph,
  companyId,
  searchable = false,
  onSelectNode,
}: {
  graph: Graph;
  companyId?: string;
  searchable?: boolean;
  onSelectNode?: (node: GraphNode | null, edges: GraphEdge[]) => void;
}) {
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 600, height: 600 });
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hiddenCats, setHiddenCats] = useState<Set<NodeCategory>>(new Set());
  const [query, setQuery] = useState("");
  const [chainlight, setChainlight] = useState<{
    nodes: Set<string>;
    links: Set<string>;
  } | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () =>
      setSize({ width: el.clientWidth, height: el.clientHeight });
    measure();
    const obs = new ResizeObserver(measure);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // Category filtering (company always survives).
  const filtered = useMemo(() => {
    const nodes = graph.nodes.filter(
      (n) => n.category === "company" || !hiddenCats.has(n.category),
    );
    const ids = new Set(nodes.map((n) => n.id));
    const edges = graph.edges.filter(
      (e) => ids.has(e.source) && ids.has(e.target),
    );
    return { nodes, edges };
  }, [graph, hiddenCats]);

  const data = useMemo(
    () => ({
      nodes: filtered.nodes.map((n) => ({ ...n })) as FGNode[],
      links: filtered.edges.map((e) => ({
        ...e,
        key: `${e.source}->${e.target}`,
      })) as FGLink[],
    }),
    [filtered],
  );

  const degree = useMemo(() => {
    const d = new Map<string, number>();
    for (const e of filtered.edges) {
      d.set(e.source, (d.get(e.source) ?? 0) + 1);
      d.set(e.target, (d.get(e.target) ?? 0) + 1);
    }
    return d;
  }, [filtered]);

  const neighborhood = useMemo(() => {
    const map = new Map<string, { nodes: Set<string>; links: Set<string> }>();
    const ensure = (id: string) => {
      let entry = map.get(id);
      if (!entry) {
        entry = { nodes: new Set([id]), links: new Set() };
        map.set(id, entry);
      }
      return entry;
    };
    for (const e of filtered.edges) {
      const key = `${e.source}->${e.target}`;
      const s = ensure(e.source);
      const t = ensure(e.target);
      s.nodes.add(e.target);
      s.links.add(key);
      t.nodes.add(e.source);
      t.links.add(key);
    }
    return map;
  }, [filtered]);

  // The active "spotlight": an edge-click chain wins, then a clicked node's
  // neighborhood, then a hovered node's. Null = calm default view.
  const context = useMemo(() => {
    if (chainlight) return { ...chainlight, soft: false };
    const focus = selectedId ?? hoverId;
    if (focus && neighborhood.has(focus)) {
      const n = neighborhood.get(focus)!;
      return { nodes: n.nodes, links: n.links, soft: focus === hoverId && !selectedId };
    }
    return null;
  }, [chainlight, selectedId, hoverId, neighborhood]);

  const radiusOf = useCallback(
    (n: FGNode) =>
      n.category === "company"
        ? 11
        : Math.min(8, 3.2 + Math.sqrt(degree.get(n.id) ?? 1) * 1.15),
    [degree],
  );

  // Spread the layout out: stronger repulsion, longer links, collision.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.d3Force("charge")?.strength(-160);
    fg.d3Force("link")?.distance(62);
    fg.d3Force(
      "collide",
      forceCollide<any>()
        .radius((n: any) => radiusOf(n as FGNode) + 13)
        .strength(0.9),
    );
    fg.d3ReheatSimulation?.();
  }, [data, radiusOf]);

  // Fit the layout to the viewport as the simulation settles (it keeps
  // expanding for a couple of seconds after the first paint).
  useEffect(() => {
    const fit = () => {
      if (!selectedId && !chainlight) fgRef.current?.zoomToFit(500, 60);
    };
    const timers = [900, 2200, 3800].map((ms) => setTimeout(fit, ms));
    return () => timers.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const chainsThroughEdge = useCallback(
    (link: FGLink): string[][] => {
      const s = endpointId(link.source);
      const t = endpointId(link.target);
      if (!companyId) return [[s, t]];
      const incoming = new Map<string, string[]>();
      for (const e of filtered.edges) {
        const arr = incoming.get(e.target) ?? [];
        arr.push(e.source);
        incoming.set(e.target, arr);
      }
      const chains: string[][] = [];
      const walk = (path: string[]) => {
        if (path.length > 4) return;
        if (path.length >= 2) chains.push([...path]);
        for (const src of incoming.get(path[0]) ?? [])
          if (!path.includes(src)) walk([src, ...path]);
      };
      walk([companyId]);
      const through = chains.filter((c) =>
        c.some((n, i) => n === s && c[i + 1] === t),
      );
      return through.length ? through : [[s, t]];
    },
    [filtered, companyId],
  );

  const clearAll = useCallback(() => {
    setChainlight(null);
    setSelectedId(null);
    onSelectNode?.(null, []);
  }, [onSelectNode]);

  const handleNodeClick = useCallback(
    (node: any) => {
      const n = node as FGNode;
      setChainlight(null);
      setSelectedId(n.id);
      onSelectNode?.(
        n,
        filtered.edges.filter((e) => e.source === n.id || e.target === n.id),
      );
      if (n.x != null && n.y != null) fgRef.current?.centerAt(n.x, n.y, 500);
    },
    [filtered, onSelectNode],
  );

  const handleLinkClick = useCallback(
    (link: any) => {
      const chains = chainsThroughEdge(link as FGLink);
      const nodes = new Set<string>();
      const links = new Set<string>();
      for (const chain of chains) {
        chain.forEach((n) => nodes.add(n));
        for (let i = 0; i < chain.length - 1; i++)
          links.add(`${chain[i]}->${chain[i + 1]}`);
      }
      setSelectedId(null);
      onSelectNode?.(null, []);
      setChainlight({ nodes, links });
    },
    [chainsThroughEdge, onSelectNode],
  );

  const flyTo = useCallback(
    (id: string) => {
      const node = (fgRef.current?.graphData()?.nodes ?? []).find(
        (n: FGNode) => n.id === id,
      );
      if (!node) return;
      handleNodeClick(node);
      fgRef.current?.zoom(3.2, 600);
      setQuery("");
    },
    [handleNodeClick],
  );

  const categories = useMemo(() => {
    const present = new Set(graph.nodes.map((n) => n.category));
    return (Object.keys(CATEGORY_COLORS) as NodeCategory[]).filter(
      (c) => present.has(c) && c !== "company",
    );
  }, [graph]);

  const hits = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return filtered.nodes
      .filter((n) => n.label.toLowerCase().includes(q))
      .slice(0, 6);
  }, [query, filtered]);

  return (
    <div ref={containerRef} className="relative h-full w-full overflow-hidden">
      <ForceGraph2D
        ref={fgRef}
        width={size.width}
        height={size.height}
        graphData={data}
        backgroundColor={BG}
        cooldownTicks={140}
        onEngineStop={() => {
          if (!selectedId && !chainlight) fgRef.current?.zoomToFit(600, 70);
        }}
        nodeId="id"
        nodeLabel={() => ""}
        nodeCanvasObject={(node: any, ctx, globalScale) => {
          const n = node as FGNode;
          const isCompany = n.category === "company";
          const inContext = context?.nodes.has(n.id) ?? false;
          const dimmed = context !== null && !inContext;
          const hovered = hoverId === n.id;
          const selected = selectedId === n.id;
          const r = radiusOf(n);
          const color = CATEGORY_COLORS[n.category] ?? "#94A3B8";

          ctx.globalAlpha = dimmed ? (context!.soft ? 0.22 : 0.1) : 1;

          // soft outer ring on the focal node
          if (selected || isCompany) {
            ctx.beginPath();
            ctx.arc(n.x!, n.y!, r + 3.5, 0, 2 * Math.PI);
            ctx.strokeStyle = `${color}55`;
            ctx.lineWidth = 1.2;
            ctx.stroke();
          }
          if (hovered || selected || isCompany) {
            ctx.shadowColor = color;
            ctx.shadowBlur = hovered || selected ? 16 : 9;
          }
          ctx.beginPath();
          ctx.arc(n.x!, n.y!, r, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
          ctx.shadowBlur = 0;

          // Labels: company always; context members always; otherwise only
          // when zoomed well in. Pill background keeps them readable.
          const showLabel =
            isCompany || (context !== null ? inContext : globalScale >= 1.9);
          if (showLabel) {
            const fontSize = Math.min(
              isCompany ? 15 : 12,
              Math.max(
                (isCompany ? 13 : 11) / globalScale,
                isCompany ? 3.6 : 3,
              ),
            );
            ctx.font = `${isCompany ? "600 " : ""}${fontSize}px Inter, sans-serif`;
            const label = n.label;
            const tw = ctx.measureText(label).width;
            const pad = fontSize * 0.35;
            const ly = n.y! + r + 2.5;
            ctx.fillStyle = "rgba(10,14,26,0.88)";
            const bx = n.x! - tw / 2 - pad;
            const by = ly - pad * 0.5;
            const bw = tw + pad * 2;
            const bh = fontSize + pad;
            ctx.beginPath();
            ctx.roundRect(bx, by, bw, bh, fontSize * 0.3);
            ctx.fill();
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillStyle = dimmed
              ? "#475569"
              : isCompany || selected || hovered
                ? "#F1F5F9"
                : "#B6C2D4";
            ctx.fillText(label, n.x!, ly);
          }
          ctx.globalAlpha = 1;
        }}
        nodePointerAreaPaint={(node: any, color, ctx) => {
          const n = node as FGNode;
          ctx.beginPath();
          ctx.arc(n.x!, n.y!, radiusOf(n) + 4, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
        }}
        linkColor={(link: any) => {
          const l = link as FGLink;
          const base = l.sign === "positive" ? "#10B981" : "#EF4444";
          if (context === null) return base + "50";
          return context.links.has(l.key)
            ? base
            : context.soft
              ? base + "18"
              : "#161d2e";
        }}
        linkWidth={(link: any) => {
          const l = link as FGLink;
          const w = CONFIDENCE_WIDTH[l.confidence] ?? 1;
          return context?.links.has(l.key) ? w * 1.7 : w;
        }}
        linkDirectionalArrowLength={3.2}
        linkDirectionalArrowRelPos={0.6}
        linkDirectionalParticles={(link: any) =>
          context?.links.has((link as FGLink).key) ? 2 : 0
        }
        linkDirectionalParticleSpeed={0.0065}
        linkDirectionalParticleWidth={2.4}
        linkDirectionalParticleColor={(link: any) =>
          (link as FGLink).sign === "positive" ? "#34D399" : "#F87171"
        }
        onNodeClick={handleNodeClick}
        onLinkClick={handleLinkClick}
        onNodeHover={(node: any) => setHoverId(node ? (node as FGNode).id : null)}
        onBackgroundClick={clearAll}
      />

      {/* search (explorer) */}
      {searchable && (
        <div className="absolute left-4 top-4 w-56">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find a node…"
            className="w-full rounded-lg border border-line bg-panel/90 px-3 py-2 text-xs text-slate-200 placeholder-slate-600 outline-none backdrop-blur transition focus:border-accent/60"
          />
          {hits.length > 0 && (
            <div className="panel mt-1 overflow-hidden py-1 shadow-xl shadow-black/50">
              {hits.map((h) => (
                <button
                  key={h.id}
                  onClick={() => flyTo(h.id)}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-slate-300 transition hover:bg-accent/10 hover:text-slate-100"
                >
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ background: CATEGORY_COLORS[h.category] }}
                  />
                  {h.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* legend = category filters */}
      <div className="panel absolute bottom-4 left-4 max-w-[240px] bg-panel/90 p-3 backdrop-blur">
        <div className="mb-1.5 flex flex-wrap gap-1.5">
          {categories.map((c) => {
            const off = hiddenCats.has(c);
            return (
              <button
                key={c}
                onClick={() =>
                  setHiddenCats((prev) => {
                    const next = new Set(prev);
                    if (next.has(c)) next.delete(c);
                    else next.add(c);
                    return next;
                  })
                }
                title={off ? `Show ${CATEGORY_LABELS[c]}` : `Hide ${CATEGORY_LABELS[c]}`}
                className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] transition ${
                  off
                    ? "border-line/50 text-slate-600"
                    : "border-line text-slate-300 hover:border-slate-500"
                }`}
              >
                <span
                  className="inline-block h-1.5 w-1.5 rounded-full"
                  style={{
                    background: off ? "#334155" : CATEGORY_COLORS[c],
                  }}
                />
                {CATEGORY_LABELS[c]}
              </button>
            );
          })}
        </div>
        <div className="border-t border-line pt-1.5 text-[10px] leading-4 text-slate-500">
          <span className="text-pos">—</span> positive ·{" "}
          <span className="text-neg">—</span> negative · width = confidence
          <br />
          hover to spotlight · click edges to trace chains
        </div>
      </div>

      <button
        onClick={() => {
          clearAll();
          fgRef.current?.zoomToFit(600, 70);
        }}
        className="panel absolute right-4 top-4 bg-panel/90 px-3 py-1.5 text-xs text-slate-300 backdrop-blur transition hover:border-accent/60 hover:text-white"
      >
        Reset view
      </button>
    </div>
  );
}
