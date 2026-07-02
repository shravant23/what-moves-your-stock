"""Core Pydantic models (spec section 4 — the Exposure Profile)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    source_doc: str  # e.g. "FCX 10-K FY2025"
    section: str  # e.g. "Risk Factors"
    quote: str  # <=15 words, the anchoring snippet, verbatim from the filing


class Exposure(BaseModel):
    name: str  # e.g. "Copper price"
    category: Literal[
        "commodity_input",
        "commodity_output",
        "geography",
        "customer_concentration",
        "supplier_concentration",
        "interest_rates",
        "currency",
        "regulation",
        "demand_driver",
    ]
    direction: Literal["benefits_when_up", "hurt_when_up", "mixed"]
    magnitude: Literal["critical", "significant", "moderate", "minor"]
    rationale: str  # one plain-English sentence
    citations: list[Citation]


class RevenueSegment(BaseModel):
    name: str
    approx_share: str  # e.g. "~65%" or "not disclosed"
    citation: Citation | None = None


class GeographicRegion(BaseModel):
    region: str
    approx_share: str
    citation: Citation | None = None


class DebtProfile(BaseModel):
    total_debt: str  # e.g. "$9.4 billion"
    fixed_vs_floating: str
    rate_sensitivity_note: str
    citation: Citation | None = None


class ExtractedProfile(BaseModel):
    """What the LLM produces. ticker/company_name/extracted_at are attached
    from EDGAR metadata afterwards."""

    business_summary: str = Field(description="2-3 sentences, plain English")
    revenue_segments: list[RevenueSegment]
    geographic_mix: list[GeographicRegion]
    exposures: list[Exposure] = Field(description="8-20 items typically")
    debt_profile: DebtProfile


class ExposureProfile(BaseModel):
    ticker: str
    company_name: str
    business_summary: str
    revenue_segments: list[RevenueSegment]
    geographic_mix: list[GeographicRegion]
    exposures: list[Exposure]
    debt_profile: DebtProfile
    extracted_at: datetime


# ------------------------------------------------------------ sector trends


class SectorTrendLLM(BaseModel):
    """LLM-produced portion of a trend; sources/as_of attached from the
    grounded search metadata (never model-generated)."""

    topic: str  # e.g. "High-bandwidth memory supply/demand"
    scope: Literal["global", "us", "china", "europe", "asia_other", "emerging"]
    current_state: str = Field(description="2-3 sentences, present conditions only")
    direction: Literal["accelerating", "stable", "decelerating", "inflecting"]
    horizon_note: str = Field(description="How durable this trend looks and why")
    relevance_to_company: str = Field(description="One sentence tying it to the ticker")


class SectorTrend(SectorTrendLLM):
    sources: list[str]  # URLs from the web search — REQUIRED, min 2
    as_of: datetime
    # Name of the exposure this trend was synthesized for — lets the graph
    # layer derive the company-impact sign (trend direction x exposure direction).
    source_exposure: str | None = None


# ------------------------------------------------------------ macro report


class Chain(BaseModel):
    path: list[str]  # graph node ids, e.g. ["ai_capex","grid_investment","copper_price","fcx"]
    direction: Literal["tailwind", "headwind"]
    horizon: Literal["short_run", "long_run", "both"]
    strength: Literal["strong", "moderate", "weak"]
    explanation: str = Field(description="2-3 sentences, plain English")
    evidence: list[Citation]
    priced_in_note: str = Field(description="References actual recent price action")


class LLMMacroReport(BaseModel):
    """LLM-produced portion; ticker/generated_at attached afterwards."""

    headline: str = Field(description="One neutral sentence")
    tailwinds: list[Chain]
    headwinds: list[Chain]
    net_short_run: str = Field(description="Must weigh BOTH sides explicitly")
    net_long_run: str
    thesis_breakers: list[str] = Field(description="3-5 concrete falsifiers")
    confidence_note: str = Field(description="What the model is least sure about")


class MacroReport(LLMMacroReport):
    ticker: str
    generated_at: datetime


# ------------------------------------------------------------ causal graph


class GraphNode(BaseModel):
    id: str  # slug, e.g. "copper_price"
    label: str  # "Copper price"
    category: Literal[
        "commodity",
        "rate",
        "currency",
        "demand_driver",
        "policy",
        "region",
        "sector",
        "company",
    ]


class SeedNode(GraphNode):
    """Seed-graph node with alias keywords used to match a company's
    extracted exposures onto existing macro nodes."""

    aliases: list[str] = []


class GraphEdge(BaseModel):
    source: str
    target: str
    sign: Literal["positive", "negative"]  # source up -> target up/down
    lag: str  # e.g. "1-2 quarters"
    confidence: Literal["high", "medium", "low"]
    rationale: str
    source_note: str  # where this relationship is documented


class Graph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
