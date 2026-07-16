"""Stable data contracts for the Alert Engine.

All persisted alert documents follow the ``Alert`` shape below. UI/API
contracts derive from this schema; adding fields is safe, changing/removing
fields requires a version bump.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

AlertSeverity = Literal["critical", "high", "medium", "low", "info"]
AlertStatus = Literal[
    "open",
    "investigating",
    "resolved_awaiting_ack",  # condition cleared, awaits human ack
    "acknowledged",  # human acknowledged; may still be open
    "closed",  # terminal
]
ResolutionMethod = Literal["auto", "manual", "none"]
NotificationChannel = Literal["in_app", "email", "slack"]

# Rank used for sorting / comparisons.
SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def severity_at_least(a: str, b: str) -> bool:
    return SEVERITY_ORDER.get(a, -1) >= SEVERITY_ORDER.get(b, -1)


class AlertEvent(BaseModel):
    """A single lifecycle event on an alert (timeline entry)."""

    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    kind: Literal[
        "created",
        "updated",
        "escalated",
        "de_escalated",
        "condition_cleared",
        "acknowledged",
        "note",
        "resolved",
        "closed",
    ]
    actor_id: str | None = None
    actor_email: str | None = None
    message: str | None = None
    from_severity: AlertSeverity | None = None
    to_severity: AlertSeverity | None = None
    from_status: AlertStatus | None = None
    to_status: AlertStatus | None = None
    value: Any | None = None


class Alert(BaseModel):
    """Persisted alert document."""

    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    device_id: str
    rule_key: str  # e.g. "cpu.high", "disk.low", "offline", "software.policy"
    dimension_key: str = ""  # optional sub-key (e.g. software name/version)

    # Presentation
    title: str
    category: str = "general"
    severity: AlertSeverity
    status: AlertStatus = "open"

    # Signal
    current_value: Any | None = None
    threshold: Any | None = None
    unit: str | None = None
    duration_seconds: int | None = None  # how long the condition has been true
    recommendation: str | None = None
    health_impact: int | None = None  # optional health-score impact estimate

    # Lifecycle timestamps (ISO strings for portability)
    created_at: str
    first_detected_at: str
    last_seen_at: str
    condition_cleared_at: str | None = None
    acknowledged_at: str | None = None
    closed_at: str | None = None
    acknowledged_by: str | None = None
    acknowledged_by_email: str | None = None
    ack_note: str | None = None
    resolution_method: ResolutionMethod = "none"

    # Analytics
    occurrence_count: int = 1

    # Explainability payload (rule-defined)
    context: dict[str, Any] = Field(default_factory=dict)

    # Timeline
    events: list[AlertEvent] = Field(default_factory=list)

    # Delivery bookkeeping
    notified_channels: list[str] = Field(default_factory=list)
    last_notified_severity: AlertSeverity | None = None

    def to_public_dict(self) -> dict[str, Any]:
        d = self.model_dump()
        # Timestamps in events are datetimes; serialize.
        for e in d.get("events") or []:
            ts = e.get("ts")
            if isinstance(ts, datetime):
                e["ts"] = ts.astimezone(timezone.utc).isoformat()
        return d
