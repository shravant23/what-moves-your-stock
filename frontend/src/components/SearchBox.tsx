"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, TickerHit } from "@/lib/api";

export default function SearchBox() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<TickerHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const debounce = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (!query.trim()) {
      setHits([]);
      return;
    }
    clearTimeout(debounce.current);
    debounce.current = setTimeout(async () => {
      try {
        const results = await api.searchTickers(query.trim());
        setHits(results);
        setOpen(true);
        setActive(0);
      } catch {
        setHits([]);
      }
    }, 200);
    return () => clearTimeout(debounce.current);
  }, [query]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const go = (ticker: string) => {
    if (!ticker.trim()) return;
    router.push(`/t/${ticker.trim().toUpperCase()}`);
  };

  return (
    <div ref={boxRef} className="relative mx-auto w-full max-w-xl">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => hits.length && setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, hits.length - 1));
          else if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, 0));
          else if (e.key === "Enter") go(open && hits[active] ? hits[active].ticker : query);
          else if (e.key === "Escape") setOpen(false);
        }}
        placeholder="Enter a ticker — FCX, DAL, NVDA…"
        className="w-full rounded-xl border border-line bg-panel px-5 py-4 text-lg text-slate-100 placeholder-slate-600 shadow-lg shadow-black/30 outline-none transition focus:border-accent/70 focus:ring-2 focus:ring-accent/20"
        aria-label="Search ticker"
      />
      {open && hits.length > 0 && (
        <div className="panel absolute z-30 mt-2 w-full overflow-hidden py-1 shadow-2xl shadow-black/60">
          {hits.map((h, i) => (
            <button
              key={h.ticker}
              onMouseEnter={() => setActive(i)}
              onClick={() => go(h.ticker)}
              className={`flex w-full items-baseline gap-3 px-4 py-2.5 text-left text-sm transition ${
                i === active ? "bg-accent/10 text-slate-100" : "text-slate-300"
              }`}
            >
              <span className="w-16 shrink-0 font-semibold text-accent">{h.ticker}</span>
              <span className="truncate text-xs text-slate-400">{h.title}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
