"""Production Alert Engine V1.

Public entry points:
    from app.services.alerts import (
        evaluate_and_apply,       # run rules against a device + apply
        acknowledge_alert,
        close_alert,
        add_alert_note,
        get_active_summary,
        sweep_offline_and_lifecycle,
    )

The engine is designed to be pluggable and org-configurable. All threshold
values live in ``policies.py`` and are overridable per-org via the
``alert_policies`` collection through the /api/alert-rules API.
"""
from .contracts import (
    Alert,
    AlertEvent,
    AlertSeverity,
    AlertStatus,
    ResolutionMethod,
    NotificationChannel,
    SEVERITY_ORDER,
)
from .engine import evaluate_and_apply, evaluate_and_apply_inventory
from .store import (
    acknowledge_alert,
    add_alert_note,
    close_alert,
    force_resolve_alert,
    get_active_summary,
)
from .sweep import sweep_offline_and_lifecycle

__all__ = [
    "Alert",
    "AlertEvent",
    "AlertSeverity",
    "AlertStatus",
    "ResolutionMethod",
    "NotificationChannel",
    "SEVERITY_ORDER",
    "evaluate_and_apply",
    "evaluate_and_apply_inventory",
    "acknowledge_alert",
    "add_alert_note",
    "close_alert",
    "force_resolve_alert",
    "get_active_summary",
    "sweep_offline_and_lifecycle",
]
