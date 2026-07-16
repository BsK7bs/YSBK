"""Abstract base class for a health engine.

An engine takes a *device context* (device dict, latest metrics, inventory,
recent alerts, recent telemetry, health timeline) and returns a
``HealthAssessment``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .contracts import HealthAssessment


class HealthEngine(ABC):
    """All health engines must implement ``assess``."""

    version: str = "base"

    @abstractmethod
    def assess(self, ctx: dict[str, Any]) -> HealthAssessment:  # noqa: D401
        """Compute a ``HealthAssessment`` from a device context.

        ``ctx`` is expected to contain:
            - device: dict
            - metrics: dict         (latest agent metrics)
            - inventory: dict       (latest inventory snapshot)
            - recent_alerts: list   (last ~24h alerts)
            - recent_telemetry: list (small window of telemetry points)
            - timeline: list        (recent health timeline points, optional)
        """
