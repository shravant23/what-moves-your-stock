"use client";

import { useState } from "react";
import { Chain, ExposureProfile, MacroReport } from "@/lib/api";

const TABS = ["Overview", "Tailwinds", "Headwinds", "Long Run", "Thesis Breakers"] as const;
type Tab = (typeof TABS)[number];

const STRENGTH_STYLE: Record<Chain["strength"], string> = {
  strong: "bg-accent/15 text-accent",
  moderate: "bg-slate-400/15 text-slate-300",
  weak: "bg-slate-600/20 text-slate-500",
};

const HORIZON_LABEL: Record<Chain["horizon"], string> = {
  short_run: "short run",
  long_run: "long run",
  both: "short + long run",
};

function trimQuote(q: string, maxWords = 15): string {
  const words = q.split(/\s+/);
  return words.length <= maxWords ? q : words.slice(0, maxWords).join(" ") + "…";
}

function ChainCard({ chain, labelOf }: { chain: Chain; labelOf: (id: string) => string }) {
  const tone = chain.direction === "tailwind" ? "pos" : "neg";
  return (
    <div className="panel space-y-3 p-4">
      {/* path as connected chips */}
      <div className="flex flex-wrap items-center gap-1.5">
        {chain.path.map((node, i) => (
          <span key={i} className="flex items-center gap-1.5">
            <span
              className={`rounded-md border px-2 py-0.5 text-[11px] font-medium ${
                i === chain.path.length - 1
                  ? "border-accent/50 bg-accent/10 text-accent"
                  : "border-line bg-bg text-slate-300"
              }`}
            >
              {labelOf(node)}
            </span>
            {i < chain.path.length - 1 && (
              <span className={`text-${tone} text-xs`}>→</span>
            )}
          </span>
        ))}
      </div>

      <div className="flex gap-2">
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${STRENGTH_STYLE[chain.strength]}`}>
          {chain.strength}
        </span>
        <span className="rounded-full bg-line/60 px-2 py-0.5 text-[10px] font-medium text-slate-400">
          {HORIZON_LABEL[chain.horizon]}
        </span>
      </div>

      <p className="text-sm leading-6 text-slate-300">{chain.explanation}</p>

      <div className="rounded-lg border border-line/70 bg-bg/50 p-3 text-xs leading-5 text-slate-500">
        <span className="font-semibold text-slate-400">Priced in? </span>
        {chain.priced_in_note}
      </div>

      {chain.evidence.length > 0 && (
        <details className="group text-xs">
          <summary className="cursor-pointer select-none text-slate-500 transition hover:text-slate-300">
            {chain.evidence.length} citation{chain.evidence.length > 1 ? "s" : ""} from filings
          </summary>
          <div className="mt-2 space-y-2">
            {chain.evidence.map((c, i) => (
              <div key={i} className="rounded-md border-l-2 border-accent/40 bg-bg/60 py-1.5 pl-3 pr-2">
                <p className="italic leading-5 text-slate-400">“{trimQuote(c.quote, 24)}”</p>
                <p className="mt-0.5 text-[10px] text-slate-600">
                  {c.source_doc} · {c.section}
                </p>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

export default function ReportPanel({
  report,
  profile,
  labelOf,
}: {
  report: MacroReport;
  profile: ExposureProfile | null;
  labelOf: (id: string) => string;
}) {
  const [tab, setTab] = useState<Tab>("Overview");
  const longRun = [...report.tailwinds, ...report.headwinds].filter(
    (c) => c.horizon !== "short_run",
  );

  return (
    <div className="flex h-full flex-col">
      <div className="scrollbar-thin flex gap-1 overflow-x-auto border-b border-line px-4 pt-3">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`whitespace-nowrap rounded-t-lg px-3 py-2 text-xs font-medium transition ${
              tab === t
                ? "border border-b-0 border-line bg-panel text-slate-100"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {t}
            {t === "Tailwinds" && ` (${report.tailwinds.length})`}
            {t === "Headwinds" && ` (${report.headwinds.length})`}
          </button>
        ))}
      </div>

      <div className="scrollbar-thin flex-1 space-y-4 overflow-y-auto p-4">
        {tab === "Overview" && (
          <>
            <div className="panel p-4">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Headline
              </div>
              <p className="text-sm font-medium leading-6 text-slate-100">
                {report.headline}
              </p>
            </div>
            {profile && (
              <div className="panel p-4">
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                  {profile.company_name}
                </div>
                <p className="text-sm leading-6 text-slate-300">
                  {profile.business_summary}
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {profile.revenue_segments.map((s) => (
                    <span key={s.name} className="rounded-full bg-line/60 px-2 py-0.5 text-[10px] text-slate-400">
                      {s.name}: {s.approx_share}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <div className="panel p-4">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-pos">
                Net — short run
              </div>
              <p className="text-sm leading-6 text-slate-300">{report.net_short_run}</p>
            </div>
            <div className="panel p-4">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-accent">
                Net — long run
              </div>
              <p className="text-sm leading-6 text-slate-300">{report.net_long_run}</p>
            </div>
            <div className="panel border-warn/30 p-4">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-warn">
                Least certain about
              </div>
              <p className="text-sm leading-6 text-slate-400">{report.confidence_note}</p>
            </div>
          </>
        )}

        {tab === "Tailwinds" &&
          (report.tailwinds.length ? (
            report.tailwinds.map((c, i) => <ChainCard key={i} chain={c} labelOf={labelOf} />)
          ) : (
            <EmptyState text="No supportable tailwind chains were found." />
          ))}

        {tab === "Headwinds" &&
          (report.headwinds.length ? (
            report.headwinds.map((c, i) => <ChainCard key={i} chain={c} labelOf={labelOf} />)
          ) : (
            <EmptyState text="No supportable headwind chains were found." />
          ))}

        {tab === "Long Run" && (
          <>
            <div className="panel p-4">
              <p className="text-sm leading-6 text-slate-300">{report.net_long_run}</p>
            </div>
            {longRun.length ? (
              longRun.map((c, i) => <ChainCard key={i} chain={c} labelOf={labelOf} />)
            ) : (
              <EmptyState text="No long-run chains in this report." />
            )}
          </>
        )}

        {tab === "Thesis Breakers" && (
          <div className="panel p-4">
            <p className="mb-3 text-xs text-slate-500">
              Concrete, observable events that would falsify this analysis:
            </p>
            <ul className="space-y-3">
              {report.thesis_breakers.map((b, i) => (
                <li key={i} className="flex gap-3 text-sm leading-6 text-slate-300">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border border-neg/40 text-[10px] text-neg">
                    {i + 1}
                  </span>
                  {b}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="panel flex items-center justify-center p-8 text-xs text-slate-500">
      {text}
    </div>
  );
}
