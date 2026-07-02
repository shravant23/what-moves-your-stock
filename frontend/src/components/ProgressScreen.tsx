"use client";

import { JobStatus } from "@/lib/api";

const STAGE_ORDER = [
  "fetching_filings",
  "extracting_profile",
  "verifying_citations",
  "synthesizing_trends",
  "pulling_macro",
  "tracing_chains",
  "writing_report",
];

const STAGE_LABELS: Record<string, string> = {
  fetching_filings: "Fetching filings from EDGAR",
  extracting_profile: "Extracting exposure profile",
  verifying_citations: "Verifying citations against filings",
  synthesizing_trends: "Scanning current sector & global conditions",
  pulling_macro: "Pulling macro series and price action",
  tracing_chains: "Tracing causal chains through the graph",
  writing_report: "Writing the report",
};

export default function ProgressScreen({
  ticker,
  job,
}: {
  ticker: string;
  job: JobStatus | null;
}) {
  const currentIdx = job ? STAGE_ORDER.indexOf(job.stage) : -1;

  return (
    <div className="flex min-h-[70vh] items-center justify-center p-6">
      <div className="panel w-full max-w-md p-8">
        <div className="mb-1 text-sm font-medium text-accent">
          Analyzing {ticker}
        </div>
        <p className="mb-6 text-xs text-slate-500">
          A full analysis reads the latest filings, live macro data, and
          current sector conditions — typically 1–3 minutes.
        </p>

        <div className="mb-6 h-1.5 overflow-hidden rounded-full bg-line">
          <div
            className="h-full rounded-full bg-accent transition-all duration-700"
            style={{ width: `${job?.percent ?? 2}%` }}
          />
        </div>

        <ol className="space-y-3">
          {STAGE_ORDER.map((stage, i) => {
            const state =
              currentIdx === -1
                ? "pending"
                : i < currentIdx
                  ? "done"
                  : i === currentIdx
                    ? "active"
                    : "pending";
            return (
              <li key={stage} className="flex items-center gap-3 text-sm">
                <span
                  className={
                    state === "done"
                      ? "flex h-5 w-5 items-center justify-center rounded-full bg-pos/20 text-[10px] text-pos"
                      : state === "active"
                        ? "h-5 w-5 animate-pulse rounded-full border-2 border-accent"
                        : "h-5 w-5 rounded-full border border-line"
                  }
                >
                  {state === "done" ? "✓" : ""}
                </span>
                <span
                  className={
                    state === "active"
                      ? "text-slate-100"
                      : state === "done"
                        ? "text-slate-400"
                        : "text-slate-600"
                  }
                >
                  {STAGE_LABELS[stage]}…
                </span>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
