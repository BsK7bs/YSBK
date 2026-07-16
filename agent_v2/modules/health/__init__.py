"""Module 7: Health Engine (client-side).

Lightweight, deterministic health snapshot computed on the endpoint. The
authoritative health scoring lives in the backend (see
``services/health/engine_v1.py``) — this local engine is a **belt-and-braces**
layer that (a) helps offline diagnostics, and (b) enriches telemetry frames
with a fast pre-score for edge cases where the WS is degraded.

Public API:
    class HealthEngine:
        def score(metrics: dict) -> ClientHealthSnapshot
"""
from .engine import HealthEngine, ClientHealthSnapshot  # noqa: F401

__all__ = ["HealthEngine", "ClientHealthSnapshot"]
