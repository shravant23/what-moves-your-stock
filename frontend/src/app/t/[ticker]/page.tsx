"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import NodeDrawer from "@/components/NodeDrawer";

const NetworkGraph = dynamic(() => import("@/components/NetworkGraph"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-sm text-slate-500">
      Loading graph…
    </div>
  ),
});
import ProgressScreen from "@/components/ProgressScreen";
import ReportPanel from "@/components/ReportPanel";
import {
  api,
  ExposureProfile,
  Graph,
  GraphEdge,
  GraphNode,
  JobStatus,
  MacroReport,
} from "@/lib/api";

type Phase = "checking" | "analyzing" | "ready" | "error";

export default function AnalysisPage({ params }: { params: { ticker: string } }) {
  const ticker = params.ticker.toUpperCase();
  const [phase, setPhase] = useState<Phase>("checking");
  const [job, setJob] = useState<JobStatus | null>(null);
  const [report, setReport] = useState<MacroReport | null>(null);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [profile, setProfile] = useState<ExposureProfile | null>(null);
  const [error, setError] = useState<string>("");
  const [selected, setSelected] = useState<{ node: GraphNode; edges: GraphEdge[] } | null>(null);
  const [view, setView] = useState<"exposures" | "full">("exposures");
  const pollRef = useRef<ReturnType<typeof setInterval>>();

  const loadAll = useCallback(async () => {
    const [r, g, p] = await Promise.all([
      api.report(ticker),
      api.tickerGraph(ticker),
      api.profile(ticker),
    ]);
    setReport(r);
    setGraph(g);
    setProfile(p);
    setPhase("ready");
  }, [ticker]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        await loadAll(); // cached report -> straight to ready
        return;
      } catch {
        /* not analyzed yet — kick off the pipeline */
      }
      try {
        const first = await api.analyze(ticker);
        if (cancelled) return;
        setJob(first);
        setPhase("analyzing");
        if (first.status === "done") {
          await loadAll();
          return;
        }
        pollRef.current = setInterval(async () => {
          try {
            const s = await api.status(first.job_id);
            if (cancelled) return;
            setJob(s);
            if (s.status === "done") {
              clearInterval(pollRef.current);
              await loadAll();
            } else if (s.status === "error") {
              clearInterval(pollRef.current);
              setError(s.error ?? "Analysis failed.");
              setPhase("error");
            }
          } catch {
            /* transient poll failure — keep polling */
          }
        }, 1500);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Something went wrong.");
          setPhase("error");
        }
      }
    })();

    return () => {
      cancelled = true;
      clearInterval(pollRef.current);
    };
  }, [ticker, loadAll]);

  const labelOf = useMemo(() => {
    const map = new Map(graph?.nodes.map((n) => [n.id, n.label]) ?? []);
    return (id: string) => map.get(id) ?? id;
  }, [graph]);

  // "Direct exposures" = the company + everything wired straight into it
  // (plus attached trend nodes). "Full web" adds the upstream macro context.
  const displayGraph = useMemo(() => {
    if (!graph) return null;
    if (view === "full") return graph;
    const companyId = ticker.toLowerCase();
    const keep = new Set([companyId]);
    for (const e of graph.edges) if (e.target === companyId) keep.add(e.source);
    for (const e of graph.edges)
      if (e.source.includes("_trend_") && keep.has(e.target)) keep.add(e.source);
    return {
      nodes: graph.nodes.filter((n) => keep.has(n.id)),
      edges: graph.edges.filter((e) => keep.has(e.source) && keep.has(e.target)),
    };
  }, [graph, view, ticker]);

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
        <span className="text-sm font-semibold text-accent">{ticker}</span>
        {profile && (
          <span className="hidden truncate text-xs text-slate-500 sm:block">
            {profile.company_name}
          </span>
        )}
        <Link
          href="/graph"
          className="ml-auto text-xs text-slate-500 transition hover:text-accent"
        >
          Graph explorer
        </Link>
      </header>

      {phase === "checking" && (
        <div className="flex flex-1 items-center justify-center text-sm text-slate-500">
          Checking for an existing analysis…
        </div>
      )}

      {phase === "analyzing" && <ProgressScreen ticker={ticker} job={job} />}

      {phase === "error" && (
        <div className="flex flex-1 items-center justify-center p-6">
          <div className="panel max-w-md p-8 text-center">
            <div className="mb-2 text-sm font-semibold text-neg">Analysis failed</div>
            <p className="mb-4 text-xs leading-5 text-slate-400">{error}</p>
            <Link
              href="/"
              className="rounded-lg border border-line px-4 py-2 text-xs text-slate-300 transition hover:border-accent/60 hover:text-accent"
            >
              ← Back to search
            </Link>
          </div>
        </div>
      )}

      {phase === "ready" && report && graph && (
        <div className="flex flex-1 flex-col overflow-hidden lg:flex-row">
          {/* left 60%: network map */}
          <div className="relative h-[45vh] border-b border-line lg:h-auto lg:w-[60%] lg:border-b-0 lg:border-r">
            <NetworkGraph
              key={view}
              graph={displayGraph ?? graph}
              companyId={ticker.toLowerCase()}
              onSelectNode={(node, edges) =>
                setSelected(node ? { node, edges } : null)
              }
            />
            {/* view toggle */}
            <div className="panel absolute left-4 top-4 flex overflow-hidden bg-panel/90 p-0.5 backdrop-blur">
              {(
                [
                  ["exposures", "Direct exposures"],
                  ["full", "Full web"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  onClick={() => setView(value)}
                  className={`rounded-[10px] px-3 py-1.5 text-xs font-medium transition ${
                    view === value
                      ? "bg-accent/15 text-accent"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {selected && (
              <NodeDrawer
                node={selected.node}
                edges={selected.edges}
                labelOf={labelOf}
                onClose={() => setSelected(null)}
              />
            )}
          </div>

          {/* right 40%: report */}
          <div className="flex-1 overflow-hidden lg:w-[40%]">
            <ReportPanel report={report} profile={profile} labelOf={labelOf} />
          </div>
        </div>
      )}

      <footer className="border-t border-line/60 py-2 text-center text-[10px] text-slate-600">
        Prism is a research tool, not investment advice.
      </footer>
    </main>
  );
}
