"""Stable data contracts for the Health Score engine.

All engines (V1 rule-based, V2 ML, V3 AI) must return objects that conform
to ``HealthAssessment`` so the API/frontend never changes when the engine
is swapped.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


HealthTier = Literal["excellent", "good", "warning", "critical"]
HealthTrend = Literal["improving", "stable", "declining", "unknown"]
Severity = Literal["ok", "low", "medium", "high", "critical", "unknown"]


def tier_for_score(score: float | int | None) -> HealthTier:
    """Fixed tier thresholds (do not change without a product decision)."""
    if score is None:
        return "critical"
    s = float(score)
    if s >= 90:
        return "excellent"
    if s >= 75:
        return "good"
    if s >= 50:
        return "warning"
    return "critical"


class MetricEvaluation(BaseModel):
    """Result for a single metric contribution to the overall score.

    Missing metrics: ``evaluated=False`` and ``deduction=0``. The metric is
    kept in the response as "Not Evaluated" so the UI can show it as such.
    """

    model_config = ConfigDict(extra="ignore")

    key: str
    label: str
    category: str = "general"
    weight: int = 0
    evaluated: bool = False
    current_value: Any = None
    normal_range: str | None = None
    unit: str | None = None
    severity: Severity = "unknown"
    deduction: float = 0.0
    reason: str | None = None
    recommendation: str | None = None


class HealthAssessment(BaseModel):
    """Full health assessment payload. Stable across engine versions."""

    model_config = ConfigDict(extra="ignore")

    # Meta
    engine_version: str = "v1-rule-based"
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Headline
    score: int = 100  # 0..100
    tier: HealthTier = "excellent"
    trend: HealthTrend = "unknown"

    # Signal quality
    data_completeness_percent: int = 100  # sum(weight of evaluated) / 100
    confidence_percent: int = 0  # blended from completeness + timeline samples
    failure_risk_percent: int = 0  # derived from severity & score

    # Explainability
    evaluated_metrics: list[MetricEvaluation] = Field(default_factory=list)
    missing_metrics: list[MetricEvaluation] = Field(default_factory=list)

    # Convenience aggregates
    total_deduction: float = 0.0
    total_weight_evaluated: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        """JSON-serializable dict (datetimes as isoformat)."""
        d = self.model_dump()
        ca = d.get("computed_at")
        if isinstance(ca, datetime):
            d["computed_at"] = ca.astimezone(timezone.utc).isoformat()
        return d
