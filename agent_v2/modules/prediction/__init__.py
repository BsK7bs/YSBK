"""Module 8: Prediction Engine (client-side).

Cheap, rule-based short-horizon predictors that produce **hints** the backend
can cross-reference against its ML models. Runs at the same cadence as
telemetry so we don't waste cycles.
"""
from .engine import PredictionEngine, PredictionHint  # noqa: F401

__all__ = ["PredictionEngine", "PredictionHint"]
