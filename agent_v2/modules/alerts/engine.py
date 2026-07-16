from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LocalAlert:
    kind: str                  # cpu_high | ram_high | temp_high | disk_low | ...
    severity: str              # info | warning | high | critical
    value: float
    threshold: float
    message: str


class AlertEngine:
    """Threshold-based client-side alert evaluator.

    Uses conservative defaults so we don't spam the backend — the *real* alert
    engine on the server side owns dwell + escalation + notification.
    """

    _RULES: list[tuple[str, str, float, str, str]] = [
        # (metric, kind, threshold, severity, message_template)
        ("cpu_pct",       "cpu_high",   95.0, "high",     "CPU at {v:.0f}%"),
        ("cpu_pct",       "cpu_high",   85.0, "warning",  "CPU elevated at {v:.0f}%"),
        ("ram_pct",       "ram_high",   95.0, "high",     "Memory saturated at {v:.0f}%"),
        ("temp_c",        "temp_high",  95.0, "critical", "Thermal critical at {v:.0f}°C"),
        ("temp_c",        "temp_high",  85.0, "high",     "Thermal high at {v:.0f}°C"),
        ("disk_used_pct", "disk_low",   95.0, "high",     "Disk almost full at {v:.0f}%"),
    ]

    def evaluate(self, metrics: dict[str, Any]) -> list[LocalAlert]:
        out: list[LocalAlert] = []
        seen_kinds: set[str] = set()
        for metric_key, kind, thr, sev, msg in self._RULES:
            if kind in seen_kinds:
                continue  # only emit the most severe hit per kind
            v = metrics.get(metric_key)
            try:
                fv = float(v) if v is not None else None
            except (TypeError, ValueError):
                fv = None
            if fv is None or fv < thr:
                continue
            out.append(LocalAlert(kind=kind, severity=sev, value=fv,
                                  threshold=thr, message=msg.format(v=fv)))
            seen_kinds.add(kind)
        return out
