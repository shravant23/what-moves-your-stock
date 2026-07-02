export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------- types

export interface Citation {
  source_doc: string;
  section: string;
  quote: string;
}

export interface Exposure {
  name: string;
  category: string;
  direction: "benefits_when_up" | "hurt_when_up" | "mixed";
  magnitude: "critical" | "significant" | "moderate" | "minor";
  rationale: string;
  citations: Citation[];
}

export interface ExposureProfile {
  ticker: string;
  company_name: string;
  business_summary: string;
  revenue_segments: { name: string; approx_share: string; citation: Citation | null }[];
  geographic_mix: { region: string; approx_share: string; citation: Citation | null }[];
  exposures: Exposure[];
  debt_profile: {
    total_debt: string;
    fixed_vs_floating: string;
    rate_sensitivity_note: string;
    citation: Citation | null;
  };
  extracted_at: string;
}

export type NodeCategory =
  | "commodity" | "rate" | "currency" | "demand_driver"
  | "policy" | "region" | "sector" | "company";

export interface GraphNode {
  id: string;
  label: string;
  category: NodeCategory;
}

export interface GraphEdge {
  source: string;
  target: string;
  sign: "positive" | "negative";
  lag: string;
  confidence: "high" | "medium" | "low";
  rationale: string;
  source_note: string;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Chain {
  path: string[];
  direction: "tailwind" | "headwind";
  horizon: "short_run" | "long_run" | "both";
  strength: "strong" | "moderate" | "weak";
  explanation: string;
  evidence: Citation[];
  priced_in_note: string;
}

export interface MacroReport {
  ticker: string;
  headline: string;
  tailwinds: Chain[];
  headwinds: Chain[];
  net_short_run: string;
  net_long_run: string;
  thesis_breakers: string[];
  confidence_note: string;
  generated_at: string;
}

export interface JobStatus {
  job_id: string;
  ticker: string;
  status: "running" | "done" | "error";
  stage: string;
  stage_label: string;
  percent: number;
  error: string | null;
}

export interface TickerHit {
  ticker: string;
  title: string;
}

// -------------------------------------------------------------- fetchers

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export const api = {
  searchTickers: (q: string) =>
    getJSON<TickerHit[]>(`/tickers?q=${encodeURIComponent(q)}`),
  analyze: async (ticker: string): Promise<JobStatus> => {
    const res = await fetch(`${API_BASE}/analyze/${ticker}`, { method: "POST" });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `Request failed (${res.status})`);
    }
    return res.json();
  },
  status: (jobId: string) => getJSON<JobStatus>(`/status/${jobId}`),
  report: (ticker: string) => getJSON<MacroReport>(`/report/${ticker}`),
  profile: (ticker: string) => getJSON<ExposureProfile>(`/profile/${ticker}`),
  tickerGraph: (ticker: string) => getJSON<Graph>(`/graph/${ticker}`),
  fullGraph: () => getJSON<Graph>(`/graph`),
};

// ------------------------------------------------------------ palette

export const CATEGORY_COLORS: Record<NodeCategory, string> = {
  company: "#3B82F6",
  commodity: "#F59E0B",
  rate: "#A78BFA",
  currency: "#22D3EE",
  demand_driver: "#E879F9",
  policy: "#FACC15",
  region: "#FB7185",
  sector: "#94A3B8",
};

export const CATEGORY_LABELS: Record<NodeCategory, string> = {
  company: "Company",
  commodity: "Commodity",
  rate: "Rates & credit",
  currency: "Currency",
  demand_driver: "Demand driver",
  policy: "Policy",
  region: "Region",
  sector: "Sector",
};
