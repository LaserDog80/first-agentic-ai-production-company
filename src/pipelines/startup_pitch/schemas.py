"""Pydantic schemas for the Startup Pitch pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TargetSegment(BaseModel):
    name: str
    description: str
    pain_point: str
    priority: Literal["primary", "secondary"]


class StrategicFrame(BaseModel):
    value_proposition: str
    target_segments: list[TargetSegment]
    strategic_thesis: str
    key_assumptions: list[str]
    moat_hypothesis: str
    research_brief: str
    model_brief: str
    financial_brief: str


class Competitor(BaseModel):
    name: str
    description: str
    funding: str = ""
    differentiator: str
    source: str = ""


class MarketTrend(BaseModel):
    trend: str
    relevance: str
    source: str = ""


class CustomerSignal(BaseModel):
    signal: str
    source: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"


class MarketSize(BaseModel):
    tam: str
    sam: str
    som: str
    growth_rate: str = ""


class MarketResearch(BaseModel):
    market_size: MarketSize
    competitors: list[Competitor]
    trends: list[MarketTrend]
    customer_signals: list[CustomerSignal] = []
    barriers: list[str] = []
    key_insight: str


class RevenueModel(BaseModel):
    type: str
    description: str
    pricing: str


class UnitEconomics(BaseModel):
    cac_estimate: str
    ltv_estimate: str
    payback_period: str
    assumptions: str = ""


class GoToMarket(BaseModel):
    strategy: str
    channels: list[str]
    launch_plan: str = ""


class Operations(BaseModel):
    team_needed: list[str]
    tech_requirements: str
    timeline: str = ""


class KeyMetric(BaseModel):
    metric: str
    target: str
    rationale: str = ""


class BusinessModel(BaseModel):
    revenue_model: RevenueModel
    unit_economics: UnitEconomics
    go_to_market: GoToMarket
    partnerships: list[str] = []
    operations: Operations
    key_metrics: list[KeyMetric]


class YearProjection(BaseModel):
    revenue: str
    costs: str
    burn_rate: str
    headcount: str


class FundingAsk(BaseModel):
    amount: str
    use_of_funds: list[str]
    runway: str


class Financials(BaseModel):
    summary: str
    year_1: YearProjection
    year_2: YearProjection
    year_3: YearProjection
    funding_ask: FundingAsk
    key_assumptions: list[str]
    sensitivity: str = ""


class PitchAsk(BaseModel):
    amount: str
    use_of_funds: str
    milestones: list[str]


class InvestorPitch(BaseModel):
    title: str
    tagline: str
    problem: str
    solution: str
    market_opportunity: str
    business_model: str
    traction: str = ""
    competitive_advantage: str
    team_needs: str
    financials_summary: str
    vision: str
    the_ask: PitchAsk


class ReviewedPitch(BaseModel):
    approved: bool
    pitch: InvestorPitch | None = None
    investor_notes: str = ""
    strengths: list[str] = []
    risks: list[str] = []
    questions_to_expect: list[str] = []
    rework_request: dict | None = None
