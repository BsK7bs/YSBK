"""Health scoring engine (modular, versioned).

Public API:
    from app.services.health import get_engine, assess_device

The engine returns an ``HealthAssessment`` with a stable schema so that
future engines (V2 ML, V3 AI recommendations) can be plugged in without
requiring API or frontend changes.
"""
from .contracts import (
    HealthAssessment,
    MetricEvaluation,
    HealthTier,
    HealthTrend,
    Severity,
    tier_for_score,
)
from .registry import get_engine, assess_device

__all__ = [
    "HealthAssessment",
    "MetricEvaluation",
    "HealthTier",
    "HealthTrend",
    "Severity",
    "tier_for_score",
    "get_engine",
    "assess_device",
]
