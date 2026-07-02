"use client";

import {
  CATEGORY_COLORS,
  CATEGORY_LABELS,
  GraphEdge,
  GraphNode,
} from "@/lib/api";

export default function NodeDrawer({
  node,
  edges,
  labelOf,
  onClose,
}: {
  node: GraphNode;
  edges: GraphEdge[];
  labelOf: (id: string) => string;
  onClose: () => void;
}) {
  const inbound = edges.filter((e) => e.target === node.id);
  const outbound = edges.filter((e) => e.source === node.id);

  return (
    <div className="panel absolute inset-y-4 right-4 z-20 flex w-[340px] max-w-[85%] flex-col overflow-hidden shadow-2xl shadow-black/50">
      <div className="flex items-start justify-between border-b border-line p-4">
        <div>
          <div className="text-base font-semibold text-slate-100">
            {node.label}
          </div>
          <span
            className="mt-1 inline-block rounded-full px-2 py-0.5 text-[11px] font-medium"
            style={{
              background: `${CATEGORY_COLORS[node.category]}22`,
              color: CATEGORY_COLORS[node.category],
            }}
          >
            {CATEGORY_LABELS[node.category]}
          </span>
        </div>
        <button
          onClick={onClose}
          className="rounded-md px-2 py-1 text-slate-500 transition hover:bg-line hover:text-slate-200"
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      <div className="scrollbar-thin flex-1 space-y-4 overflow-y-auto p-4">
        {[
          { title: "Influenced by", list: inbound, dir: "in" as const },
          { title: "Influences", list: outbound, dir: "out" as const },
        ].map(
          ({ title, list, dir }) =>
            list.length > 0 && (
              <div key={title}>
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  {title}
                </div>
                <div className="space-y-2">
                  {list.map((e, i) => (
                    <div
                      key={i}
                      className="rounded-lg border border-line bg-bg/60 p-2.5 text-xs"
                    >
                      <div className="mb-1 flex items-center gap-1.5 font-medium text-slate-200">
                        <span
                          className={
                            e.sign === "positive" ? "text-pos" : "text-neg"
                          }
                        >
                          {e.sign === "positive" ? "▲" : "▼"}
                        </span>
                        {dir === "in" ? labelOf(e.source) : labelOf(e.target)}
                        <span className="ml-auto text-[10px] text-slate-500">
                          {e.lag} · {e.confidence}
                        </span>
                      </div>
                      <p className="leading-5 text-slate-400">{e.rationale}</p>
                      <p className="mt-1 text-[10px] italic text-slate-600">
                        {e.source_note}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ),
        )}
        {inbound.length + outbound.length === 0 && (
          <p className="text-xs text-slate-500">No connections in this view.</p>
        )}
      </div>
    </div>
  );
}
