"""Lightweight dataclasses shared across analytics/evidence/llm/recommend layers.

Kept intentionally small — this is not an ORM. SQL access lives in each module.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KPIResult:
    kpi_key: str
    label: str
    month: str
    branch_id: Optional[str]
    actual: float
    expected: float
    change_pct: float          # (actual - expected) / expected
    unit: str


@dataclass
class DetectionResult:
    kpi: KPIResult
    z_score: float
    is_anomalous: bool
    materiality: float          # 0..1
    materiality_band: str       # low | medium | high
    method: str                 # e.g. "baseline_zscore"
    persistence_months: int = 0
    sparse_history: bool = False


@dataclass
class DriverContribution:
    driver_key: str
    label: str
    contribution_pct: float     # share of the movement attributable to this driver
    sub_drivers: list = field(default_factory=list)  # list[DriverContribution]


@dataclass
class AttributionResult:
    detection: DetectionResult
    drivers: list                # list[DriverContribution], sorted desc by |contribution_pct|
    method: str = "contribution_analysis"


@dataclass
class EvidenceItem:
    doc_id: str
    title: str
    source_type: str
    stance: str                  # SUPPORTS | CONTRADICTS | NEUTRAL
    relevance: float             # 0..1
    snippet: str
    created_on: Optional[str] = None
    freshness_status: Optional[str] = None


@dataclass
class ConfidenceResult:
    attribution: AttributionResult
    evidence: list                # list[EvidenceItem]
    confidence_score: float       # 0..1
    confidence_band: str          # HIGH | MEDIUM | LOW | ABSTAIN
    rationale: str


@dataclass
class RecommendedAction:
    driver_key: str
    lever: str
    action: str
    owner: str
    monitoring_kpi: Optional[str]


@dataclass
class InsightPackage:
    """Everything the LLM narrative layer needs — no raw DB access required."""
    confidence: ConfidenceResult
    recommendation: Optional[RecommendedAction]
    persona: str
    question: Optional[str] = None
    conversation_history: list = field(default_factory=list)
