"""Default alert policies (thresholds, dwell windows, severity mapping).

All values are org-overridable via the alert_policies collection. See the
rules module for the exact semantics of each policy key.

Design notes:
    * ``dwell_seconds`` = the condition must remain true continuously for this
      many seconds before the alert fires. This prevents spike-based false
      alarms.
    * ``escalations`` = ordered list of (dwell_seconds, threshold, severity).
      The engine walks the list bottom-up and picks the highest tier for which
      the condition has been true long enough. This gives us the
      "CPU >85% for 10min = Medium; CPU >95% for 15min = High" behavior.
    * ``resolution_grace_seconds`` = how long the condition must remain healthy
      before the alert is auto-resolved (differentiated by severity in
      ``resolution_grace_by_severity`` below).
"""
from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------
# Auto-resolution grace windows (per severity).
# --------------------------------------------------------------------------
# For high/critical the condition can clear but the alert stays in the
# "resolved_awaiting_ack" state until a human acknowledges it.
RESOLUTION_GRACE_BY_SEVERITY: dict[str, int | None] = {
    "info": 0,           # auto-resolve immediately
    "low": 5 * 60,       # 5 minutes healthy
    "medium": 10 * 60,   # 10 minutes healthy
    "high": None,        # requires ack (park in resolved_awaiting_ack)
    "critical": None,    # requires ack (park in resolved_awaiting_ack)
}

# Notify by default at these severities and above.
DEFAULT_NOTIFY_MIN_SEVERITY = "high"

# --------------------------------------------------------------------------
# Rule policies (defaults; org can override via alert_policies).
# --------------------------------------------------------------------------
DEFAULT_POLICIES: dict[str, dict[str, Any]] = {
    "cpu.high": {
        "enabled": True,
        "category": "performance",
        "title": "High CPU utilisation",
        "unit": "%",
        "recommendation": "Investigate top processes; profile background scanners.",
        "escalations": [
            {"threshold": 85.0, "dwell_seconds": 10 * 60, "severity": "medium"},
            {"threshold": 95.0, "dwell_seconds": 15 * 60, "severity": "high"},
        ],
    },
    "ram.high": {
        "enabled": True,
        "category": "performance",
        "title": "High memory utilisation",
        "unit": "%",
        "recommendation": "Identify memory-heavy processes; add RAM if this persists.",
        "escalations": [
            {"threshold": 85.0, "dwell_seconds": 10 * 60, "severity": "medium"},
            {"threshold": 95.0, "dwell_seconds": 10 * 60, "severity": "high"},
        ],
    },
    "temperature.high": {
        "enabled": True,
        "category": "thermal",
        "title": "CPU overheating",
        "unit": "°C",
        "recommendation": "Clean cooling fan and inspect thermal paste; verify airflow.",
        "escalations": [
            {"threshold": 85.0, "dwell_seconds": 2 * 60, "severity": "high"},
            {"threshold": 95.0, "dwell_seconds": 5 * 60, "severity": "critical"},
        ],
    },
    "disk.low": {
        "enabled": True,
        "category": "storage",
        "title": "High disk usage",
        "unit": "%",
        "recommendation": "Clear temp files, remove unused apps, expand the volume.",
        "escalations": [
            {"threshold": 85.0, "dwell_seconds": 60, "severity": "medium"},
            {"threshold": 90.0, "dwell_seconds": 60, "severity": "high"},
        ],
    },
    "ssd.failure": {
        "enabled": True,
        "category": "storage",
        "title": "Disk SMART failure detected",
        "recommendation": "Back up critical data immediately and replace failing drive(s).",
        # A single failing SMART assessment is enough — dwell 0.
        "escalations": [
            {"dwell_seconds": 0, "severity": "critical"},
        ],
    },
    "ssd.failure_predicted": {
        "enabled": True,
        "category": "storage",
        "title": "SSD failure predicted",
        "unit": "% confidence",
        "recommendation": "Predictive model flags this drive; back up data and replace proactively.",
        # Escalates when the prediction confidence crosses the threshold.
        "escalations": [
            {"threshold": 90.0, "dwell_seconds": 0, "severity": "critical"},
        ],
    },
    "disk.health.low": {
        "enabled": True,
        "category": "storage",
        "title": "Disk health degraded",
        "unit": "% health",
        "recommendation": "Drive health has dropped; schedule replacement before failure.",
        # NOTE: value is % remaining life; we alert when value is BELOW threshold.
        # Handled specifically in rule_disk_health (inverted comparison).
        "escalations": [
            {"threshold": 70.0, "dwell_seconds": 0, "severity": "medium"},
            {"threshold": 20.0, "dwell_seconds": 0, "severity": "critical"},
        ],
    },
    "gpu.temperature.high": {
        "enabled": True,
        "category": "thermal",
        "title": "GPU overheating",
        "unit": "°C",
        "recommendation": "Verify GPU airflow and driver limits; reduce sustained load.",
        "escalations": [
            {"threshold": 90.0, "dwell_seconds": 2 * 60, "severity": "high"},
        ],
    },
    "battery.health.low": {
        "enabled": True,
        "category": "power",
        "title": "Battery health degraded",
        "unit": "% health",
        "recommendation": "Battery has lost significant capacity; plan replacement.",
        "escalations": [
            {"threshold": 60.0, "dwell_seconds": 0, "severity": "medium"},
        ],
    },
    "fan.abnormal": {
        "enabled": True,
        "category": "thermal",
        "title": "Fan speed abnormal",
        "recommendation": "Inspect fans for wear/obstruction; verify cooling curve.",
        "escalations": [
            {"dwell_seconds": 5 * 60, "severity": "medium"},
        ],
    },
    "power.supply.failure": {
        "enabled": True,
        "category": "power",
        "title": "Power supply failure",
        "recommendation": "Replace PSU immediately; verify redundancy where available.",
        "escalations": [{"dwell_seconds": 0, "severity": "critical"}],
    },
    "memory.leak": {
        "enabled": True,
        "category": "performance",
        "title": "Memory leak detected",
        "recommendation": "Identify long-running process with monotonically growing RSS.",
        "escalations": [{"dwell_seconds": 30 * 60, "severity": "high"}],
    },
    "app.crashes.frequent": {
        "enabled": True,
        "category": "reliability",
        "title": "Frequent application crashes",
        "unit": "crashes/hour",
        "recommendation": "Check event log; update or reinstall the crashing application.",
        "escalations": [
            {"threshold": 3.0, "dwell_seconds": 60 * 60, "severity": "high"},
        ],
    },
    "auth.login_failures": {
        "enabled": True,
        "category": "security",
        "title": "Repeated login failures",
        "unit": "failures",
        "recommendation": "Review event log for brute-force attempts; lock/rotate credentials.",
        "escalations": [
            {"threshold": 5.0, "dwell_seconds": 5 * 60, "severity": "medium"},
        ],
    },
    "health.score.low": {
        "enabled": True,
        "category": "health",
        "title": "Device health score low",
        "unit": "score",
        "recommendation": "Review health deductions and remediate the highest-weight items.",
        # value is the score (0-100); we alert when BELOW threshold (inverted).
        "escalations": [
            {"threshold": 75.0, "dwell_seconds": 0, "severity": "medium"},   # 50-74
            {"threshold": 50.0, "dwell_seconds": 0, "severity": "high"},     # <50
        ],
    },
    "health.risk.high": {
        "enabled": True,
        "category": "health",
        "title": "Predicted failure risk high",
        "unit": "% risk",
        "recommendation": "Predictive model indicates elevated failure risk; investigate.",
        "escalations": [
            {"threshold": 80.0, "dwell_seconds": 0, "severity": "high"},
        ],
    },
    "system.restart": {
        "enabled": True,
        "category": "system",
        "title": "System restart detected",
        "recommendation": "Review restart cause (patch, crash, manual). Confirm services recovered.",
        "escalations": [{"dwell_seconds": 0, "severity": "low"}],
    },
    "software.new_installed": {
        "enabled": True,
        "category": "compliance",
        "title": "New software installed",
        "recommendation": "Verify the software is authorized under your policy.",
        "escalations": [{"dwell_seconds": 0, "severity": "low"}],
    },
    "software.update_available": {
        "enabled": True,
        "category": "compliance",
        "title": "Software update available",
        "recommendation": "Plan a maintenance window to update this application.",
        "escalations": [{"dwell_seconds": 0, "severity": "low"}],
    },
    "peripheral.new_connected": {
        "enabled": True,
        "category": "peripheral",
        "title": "New peripheral connected",
        "recommendation": "Verify the peripheral is authorized for this endpoint.",
        "escalations": [{"dwell_seconds": 0, "severity": "low"}],
    },
    "agent.version_outdated": {
        "enabled": True,
        "category": "system",
        "title": "Agent version outdated",
        "recommendation": "Update the Digital Twin agent to the latest version.",
        "escalations": [{"dwell_seconds": 0, "severity": "low"}],
    },
    "offline": {
        "enabled": True,
        "category": "availability",
        "title": "Device offline",
        "recommendation": "Verify power, network connectivity, and the DigitalTwinAgent service.",
        "escalations": [
            {"threshold_minutes": 5,  "severity": "low"},
            {"threshold_minutes": 10, "severity": "medium"},
            {"threshold_minutes": 30, "severity": "critical"},
        ],
    },
    "network.failure": {
        "enabled": True,
        "category": "network",
        "title": "Network connectivity issue",
        "recommendation": "Check cabling / Wi-Fi signal; verify DNS and gateway; restart adapters.",
        "escalations": [
            {"dwell_seconds": 10 * 60, "severity": "high"},
        ],
    },
    "security.antivirus_disabled": {
        "enabled": True,
        "category": "security",
        "title": "Antivirus disabled",
        "recommendation": "Re-enable antivirus protection immediately.",
        "escalations": [{"dwell_seconds": 0, "severity": "critical"}],
    },
    "security.firewall_disabled": {
        "enabled": True,
        "category": "security",
        "title": "Firewall disabled",
        "recommendation": "Re-enable the firewall to restore perimeter protection.",
        "escalations": [{"dwell_seconds": 0, "severity": "critical"}],
    },
    "updates.missing.critical": {
        "enabled": True,
        "category": "security",
        "title": "Critical OS updates missing",
        "recommendation": "Schedule a maintenance window to install critical patches.",
        "escalations": [{"dwell_seconds": 0, "severity": "medium"}],
    },
    "updates.missing.noncritical": {
        "enabled": True,
        "category": "security",
        "title": "OS updates available",
        "recommendation": "Plan a maintenance window to install pending updates.",
        "escalations": [{"dwell_seconds": 0, "severity": "low"}],
    },
    "usb.inserted": {
        "enabled": True,
        "category": "peripheral",
        "title": "USB device connected",
        "recommendation": "Verify the device is authorized for this endpoint.",
        "escalations": [{"dwell_seconds": 0, "severity": "low"}],
    },
    "software.policy": {
        "enabled": True,
        "category": "compliance",
        "title": "Software policy violation",
        "recommendation": "Review the software policy and remove or approve the software.",
        "escalations": [{"dwell_seconds": 0, "severity": "high"}],
    },
}


def merge_policy(default: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    """Return a shallow merge of default + org override."""
    if not override:
        return default
    merged = dict(default)
    for k, v in override.items():
        if v is not None:
            merged[k] = v
    return merged
