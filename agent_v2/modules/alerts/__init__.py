"""Module 9: Alert Engine (client-side).

Client-side thresholds fire hints that ride along with the telemetry frame.
The authoritative alert pipeline still lives in the backend (dwell-aware,
dedup, escalation) — this module exists so that:
  * offline agents can still emit local events to their logs, and
  * telemetry frames can carry an early-warning signal for the backend engine.
"""
from .engine import AlertEngine, LocalAlert  # noqa: F401

__all__ = ["AlertEngine", "LocalAlert"]
