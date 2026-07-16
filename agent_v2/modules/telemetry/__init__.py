"""Module 5: Telemetry Engine.

Pulls metrics from the modular collectors, frames them, and either sends live
via the WS client or queues them for later via the Offline Queue.

Public API:
    class TelemetryEngine(ws, interval)
        async run(stop_event)
        last_sent_iso: str | None
"""
from .engine import TelemetryEngine  # noqa: F401

__all__ = ["TelemetryEngine"]
