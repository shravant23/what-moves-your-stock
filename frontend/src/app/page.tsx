import Link from "next/link";
import SearchBox from "@/components/SearchBox";

const EXAMPLES = ["FCX", "DAL", "NVDA", "HD"];

const FEATURES = [
  {
    title: "The exposure web",
    body: "An interactive network map of every macro force wired into the company — commodities, rates, currencies, regions, policy — extracted from its actual SEC filings.",
  },
  {
    title: "Cited & traceable",
    body: "Every claim anchors to a verbatim quote from a 10-K or 10-Q, string-verified against the filing text. Hallucinated citations are rejected before you ever see them.",
  },
  {
    title: "Current, not textbook",
    body: "Live macro series, trailing price action, and web-sourced sector conditions — so the analysis reflects this quarter's world, and tells you what's already priced in.",
  },
];

export default function Home() {
  return (
    <main className="hero-gradient flex min-h-screen flex-col">
      <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col items-center justify-center px-6 py-20">
        <div className="mb-3 flex items-center gap-2 text-accent">
          <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
            <path d="M16 6 L27 24 L5 24 Z" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round" />
          </svg>
          <span className="text-xl font-semibold tracking-tight text-slate-100">Prism</span>
        </div>

        <h1 className="mb-3 text-center text-4xl font-semibold tracking-tight text-slate-50 sm:text-5xl">
          See what actually moves your stock
        </h1>
        <p className="mb-10 max-w-xl text-center text-sm leading-6 text-slate-400">
          Enter a ticker. Get the company&apos;s macroeconomic exposure web as an
          interactive map, and a cited report on the forces flowing through it.
        </p>

        <SearchBox />

        <div className="mt-5 flex items-center gap-2 text-xs text-slate-500">
          Try:
          {EXAMPLES.map((t) => (
            <Link
              key={t}
              href={`/t/${t}`}
              className="rounded-full border border-line bg-panel px-3 py-1 font-medium text-slate-300 transition hover:border-accent/60 hover:text-accent"
            >
              {t}
            </Link>
          ))}
        </div>

        <div className="mt-20 grid w-full gap-4 sm:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="panel p-5">
              <div className="mb-2 text-sm font-semibold text-slate-100">{f.title}</div>
              <p className="text-xs leading-5 text-slate-400">{f.body}</p>
            </div>
          ))}
        </div>

        <Link
          href="/graph"
          className="mt-10 text-xs text-slate-500 underline-offset-4 transition hover:text-accent hover:underline"
        >
          Or explore the full macro causal graph →
        </Link>
      </div>

      <footer className="border-t border-line/60 py-5 text-center text-[11px] text-slate-600">
        Prism is a research tool, not investment advice.
      </footer>
    </main>
  );
}
