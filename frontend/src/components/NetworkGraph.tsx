"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CATEGORY_COLORS,
  CATEGORY_LABELS,
  Graph,
  GraphEdge,
  GraphNode,
  NodeCategory,
} from "@/lib/api";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-sm text-slate-500">
      Loading graph…
    </div>
  ),
});

interface FGNode extends GraphNode {
  x?: number;
  y?: number;
}
interface FGLink extends Omit<GraphEdge, "source" | "target"> {
  source: FGNode | string;
  target: FGNode | string;
  key: string;
}

const CONFIDENCE_WIDTH = { high: 2.4, medium: 1.4, low: 0.7 } as const;

function endpointId(v: FGNode | string): string {
  return typeof v === "string" ? v : v.id;
}

export default function NetworkGraph({
  graph,
  companyId,
  onSelectNode,
}: {
  graph: Graph;
  companyId?: string;
  onSelectNode?: (node: GraphNode | null, edges: GraphEdge[]) => void;
}) {
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 600, height: 600 });
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<{
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

  const data = useMemo(() => {
    const nodes: FGNode[] = graph.nodes.map((n) => ({ ...n }));
    const links: FGLink[] = graph.edges.map((e) => ({
      ...e,
      key: `${e.source}->${e.target}`,
    }));
    return { nodes, links };
  }, [graph]);

  // Paths of <=4 nodes ending at the company that pass through a given edge —
  // used to light up the full chain when an edge is clicked.
  const chainsThroughEdge = useCallback(
    (link: FGLink): string[][] => {
      const s = endpointId(link.source);
      const t = endpointId(link.target);
      if (!companyId) return [[s, t]];
      const incoming = new Map<string, string[]>();
      for (const e of graph.edges) {
        const arr = incoming.get(e.target) ?? [];
        arr.push(e.source);
        incoming.set(e.target, arr);
      }
      const chains: string[][] = [];
      const walk = (path: string[]) => {
        if (path.length > 4) return;
        const head = path[0];
        if (path.length >= 2) chains.push([...path]);
        for (const src of incoming.get(head) ?? [])
          if (!path.includes(src)) walk([src, ...path]);
      };
      walk([companyId]);
      const through = chains.filter((c) =>
        c.some((n, i) => n === s && c[i + 1] === t),
      );
      return through.length ? through : [[s, t]];
    },
    [graph, companyId],
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
      setHighlight({ nodes, links });
      onSelectNode?.(null, []);
    },
    [chainsThroughEdge, onSelectNode],
  );

  const handleNodeClick = useCallback(
    (node: any) => {
      const n = node as FGNode;
      const connected = graph.edges.filter(
        (e) => e.source === n.id || e.target === n.id,
      );
      setHighlight(null);
      onSelectNode?.(n, connected);
    },
    [graph, onSelectNode],
  );

  const resetView = useCallback(() => {
    setHighlight(null);
    onSelectNode?.(null, []);
    fgRef.current?.zoomToFit(500, 60);
  }, [onSelectNode]);

  const categories = useMemo(() => {
    const present = new Set(graph.nodes.map((n) => n.category));
    return (Object.keys(CATEGORY_COLORS) as NodeCategory[]).filter((c) =>
      present.has(c),
    );
  }, [graph]);

  return (
    <div ref={containerRef} className="relative h-full w-full overflow-hidden">
      <ForceGraph2D
        ref={fgRef}
        width={size.width}
        height={size.height}
        graphData={data}
        backgroundColor="#0A0E1A"
        cooldownTicks={120}
        onEngineStop={() => fgRef.current?.zoomToFit(500, 60)}
        nodeId="id"
        nodeLabel={() => ""}
        nodeCanvasObject={(node: any, ctx, globalScale) => {
          const n = node as FGNode;
          const isCompany = n.category === "company";
          const dimmed = highlight !== null && !highlight.nodes.has(n.id);
          const hovered = hoverId === n.id;
          const r = isCompany ? 10 : 5.5;
          const color = CATEGORY_COLORS[n.category] ?? "#94A3B8";

          ctx.globalAlpha = dimmed ? 0.15 : 1;
          if (hovered || isCompany) {
            ctx.shadowColor = color;
            ctx.shadowBlur = hovered ? 18 : 10;
          }
          ctx.beginPath();
          ctx.arc(n.x!, n.y!, r, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
          ctx.shadowBlur = 0;

          const fontSize = Math.max(11 / globalScale, isCompany ? 4 : 2.6);
          ctx.font = `${isCompany ? "600 " : ""}${fontSize}px Inter, sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "top";
          ctx.fillStyle = dimmed ? "#334155" : "#CBD5E1";
          ctx.fillText(n.label, n.x!, n.y! + r + 1.5);
          ctx.globalAlpha = 1;
        }}
        nodePointerAreaPaint={(node: any, color, ctx) => {
          const n = node as FGNode;
          const r = n.category === "company" ? 12 : 8;
          ctx.beginPath();
          ctx.arc(n.x!, n.y!, r, 0, 2 * Math.PI);
          ctx.fillStyle = color;
          ctx.fill();
        }}
        linkColor={(link: any) => {
          const l = link as FGLink;
          const base = l.sign === "positive" ? "#10B981" : "#EF4444";
          if (highlight === null) return base + "99";
          return highlight.links.has(l.key) ? base : "#1E2638";
        }}
        linkWidth={(link: any) => {
          const l = link as FGLink;
          const w = CONFIDENCE_WIDTH[l.confidence] ?? 1;
          return highlight?.links.has(l.key) ? w * 1.8 : w;
        }}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={0.55}
        linkDirectionalParticles={0}
        onNodeClick={handleNodeClick}
        onLinkClick={handleLinkClick}
        onNodeHover={(node: any) => setHoverId(node ? (node as FGNode).id : null)}
        onBackgroundClick={() => {
          setHighlight(null);
          onSelectNode?.(null, []);
        }}
      />

      {/* legend */}
      <div className="panel absolute bottom-4 left-4 max-w-[220px] p-3 text-[11px] leading-5 text-slate-400">
        <div className="mb-1 flex flex-wrap gap-x-3 gap-y-0.5">
          {categories.map((c) => (
            <span key={c} className="flex items-center gap-1.5">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: CATEGORY_COLORS[c] }}
              />
              {CATEGORY_LABELS[c]}
            </span>
          ))}
        </div>
        <div className="border-t border-line pt-1">
          <span className="text-pos">— positive</span>
          {"  ·  "}
          <span className="text-neg">— negative</span>
          {"  ·  width = confidence"}
        </div>
      </div>

      <button
        onClick={resetView}
        className="panel absolute right-4 top-4 px-3 py-1.5 text-xs text-slate-300 transition hover:border-accent/60 hover:text-white"
      >
        Reset view
      </button>
    </div>
  );
}
