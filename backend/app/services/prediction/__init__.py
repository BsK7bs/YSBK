"""AI Prediction module.

Rule-engine + scikit-learn hybrid that predicts near-term hardware failures
across six failure types:

    - ssd        (SSD Failure)
    - fan        (Fan Failure)
    - cpu_thermal (CPU Overheating)
    - battery    (Battery Failure)
    - memory     (Memory Failure)
    - network    (Network Failure)

Public API:
    predict_device(ctx)  -> PredictionReport
    FAILURE_TYPES        -> list of supported failure types

The engine is designed for:
    * Explainability: every prediction carries a plain-English ``reason`` and
      an actionable ``recommendation``.
    * Confidence: reported alongside probability so the UI can gate action.
    * Modularity: sklearn models are lazily loaded, retrainable on-demand,
      and combined with rule-based signals for robustness on cold-start.
"""
from .engine import predict_device, FAILURE_TYPES, ENGINE_VERSION, PredictionReport, Prediction  # noqa: F401
