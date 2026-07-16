"""Rule evaluators for the Alert Engine.

Each rule inspects the incoming device context and returns a
``RuleTrigger`` describing whether an alert should be open (and at what
severity) or whether the condition is currently healthy.

A ``RuleTrigger`` with ``triggered=False`` and ``clear=True`` signals that
the engine should attempt to auto-resolve any existing active alert for
this rule.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .contracts import AlertSeverity
from .policies import DEFAULT_POLICIES, merge_policy


@dataclass
class RuleTrigger:
    rule_key: str
    title: str
    category: str
    triggered: bool = False
    clear: bool = False
    severity: AlertSeverity | None = None
    current_value: Any | None = None
    threshold: Any | None = None
    unit: str | None = None
    dimension_key: str = ""
    dwell_seconds: int = 0  # required dwell for the chosen severity
    duration_seconds: int = 0  # observed duration for context
    recommendation: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:
            return None
        return f
    except (TypeError, ValueError):
        return None


def _policy(policies: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
    return merge_policy(DEFAULT_POLICIES.get(key, {}), (policies or {}).get(key))


def _pick_escalation_by_value(policy: dict[str, Any], value: float | None) -> dict[str, Any] | None:
    """Given a numeric value, pick the highest escalation whose threshold is met."""
    if value is None:
        return None
    picked = None
    for esc in sorted(policy.get("escalations") or [], key=lambda e: e.get("threshold", 0)):
        thr = esc.get("threshold")
        if thr is None or value >= thr:
            picked = esc
    return picked


# ---------------------------------------------------------------------------
# Metric-based rules (dwell-aware, escalating)
# ---------------------------------------------------------------------------

def rule_cpu_high(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "cpu.high")
    v = _num((ctx.get("metrics") or {}).get("cpu_percent"))
    t = RuleTrigger(rule_key="cpu.high", title=pol["title"], category=pol["category"],
                    unit=pol.get("unit"), recommendation=pol.get("recommendation"),
                    current_value=v)
    if v is None or not pol.get("enabled", True):
        return t
    esc = _pick_escalation_by_value(pol, v)
    if esc is None:
        t.clear = True
        return t
    t.triggered = True
    t.severity = esc["severity"]
    t.threshold = esc.get("threshold")
    t.dwell_seconds = int(esc.get("dwell_seconds", 0))
    return t


def rule_ram_high(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "ram.high")
    v = _num((ctx.get("metrics") or {}).get("ram_percent"))
    t = RuleTrigger(rule_key="ram.high", title=pol["title"], category=pol["category"],
                    unit=pol.get("unit"), recommendation=pol.get("recommendation"),
                    current_value=v)
    if v is None or not pol.get("enabled", True):
        return t
    esc = _pick_escalation_by_value(pol, v)
    if esc is None:
        t.clear = True
        return t
    t.triggered = True
    t.severity = esc["severity"]
    t.threshold = esc.get("threshold")
    t.dwell_seconds = int(esc.get("dwell_seconds", 0))
    return t


def rule_temperature_high(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "temperature.high")
    v = _num((ctx.get("metrics") or {}).get("cpu_temp_c"))
    t = RuleTrigger(rule_key="temperature.high", title=pol["title"], category=pol["category"],
                    unit=pol.get("unit"), recommendation=pol.get("recommendation"),
                    current_value=v)
    if v is None or v <= 0 or not pol.get("enabled", True):
        return t
    esc = _pick_escalation_by_value(pol, v)
    if esc is None:
        t.clear = True
        return t
    t.triggered = True
    t.severity = esc["severity"]
    t.threshold = esc.get("threshold")
    t.dwell_seconds = int(esc.get("dwell_seconds", 0))
    return t


def rule_disk_low(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "disk.low")
    v = _num((ctx.get("metrics") or {}).get("disk_percent"))
    t = RuleTrigger(rule_key="disk.low", title=pol["title"], category=pol["category"],
                    unit=pol.get("unit"), recommendation=pol.get("recommendation"),
                    current_value=v)
    if v is None or not pol.get("enabled", True):
        return t
    esc = _pick_escalation_by_value(pol, v)
    if esc is None:
        t.clear = True
        return t
    t.triggered = True
    t.severity = esc["severity"]
    t.threshold = esc.get("threshold")
    t.dwell_seconds = int(esc.get("dwell_seconds", 0))
    return t


def rule_ssd_failure(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "ssd.failure")
    metrics = ctx.get("metrics") or {}
    inv = ctx.get("inventory") or {}
    smart = metrics.get("smart") or ((inv.get("disk") or {}).get("smart")) or []
    t = RuleTrigger(rule_key="ssd.failure", title=pol["title"], category=pol["category"],
                    recommendation=pol.get("recommendation"))
    if not isinstance(smart, list) or not smart or not pol.get("enabled", True):
        return t
    failing = [d for d in smart if isinstance(d, dict)
               and (d.get("assessment") or "").upper() not in ("PASS", "OK", "")]
    if not failing:
        t.clear = True
        return t
    t.triggered = True
    t.severity = pol["escalations"][0]["severity"]
    t.current_value = ", ".join([d.get("name") or d.get("model") or "drive" for d in failing[:3]])
    t.context = {"failing_drives": failing[:5]}
    return t


# ---------------------------------------------------------------------------
# Availability / connectivity rules
# ---------------------------------------------------------------------------

def rule_offline(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    """Evaluate device offline / agent-not-reporting with tiered severity.

    Uses ``last_seen`` from the device doc and ``policies['offline'].escalations``
    with ``threshold_minutes`` bands.
    """
    pol = _policy(policies, "offline")
    device = ctx.get("device") or {}
    last_seen = device.get("last_seen")
    is_online = bool(device.get("is_online"))
    t = RuleTrigger(rule_key="offline", title=pol["title"], category=pol["category"],
                    recommendation=pol.get("recommendation"))
    if not pol.get("enabled", True):
        return t
    if is_online and last_seen:
        t.clear = True
        return t
    if not last_seen:
        return t
    try:
        dt = datetime.fromisoformat(str(last_seen).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return t
    minutes = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 60.0)

    escalations = sorted(pol.get("escalations") or [],
                         key=lambda e: e.get("threshold_minutes", 0))
    picked = None
    for esc in escalations:
        thr = esc.get("threshold_minutes") or 0
        if minutes >= thr:
            picked = esc
    if not picked:
        return t
    t.triggered = True
    t.severity = picked["severity"]
    t.current_value = round(minutes, 1)
    t.threshold = picked.get("threshold_minutes")
    t.unit = "minutes offline"
    t.duration_seconds = int(minutes * 60)
    return t


def rule_network_failure(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "network.failure")
    m = ctx.get("metrics") or {}
    adapters = m.get("adapters") or []
    latency = _num(m.get("latency_ms"))
    t = RuleTrigger(rule_key="network.failure", title=pol["title"], category=pol["category"],
                    recommendation=pol.get("recommendation"))
    if not pol.get("enabled", True):
        return t
    up = [a for a in adapters if isinstance(a, dict) and a.get("is_up")]
    if adapters and not up:
        t.triggered = True
        t.severity = pol["escalations"][0]["severity"]
        t.current_value = "no active adapters"
        t.dwell_seconds = int(pol["escalations"][0].get("dwell_seconds", 0))
        return t
    if latency is not None and latency > 500:
        t.triggered = True
        t.severity = pol["escalations"][0]["severity"]
        t.current_value = f"{latency:.0f} ms"
        t.dwell_seconds = int(pol["escalations"][0].get("dwell_seconds", 0))
        return t
    t.clear = True
    return t


# ---------------------------------------------------------------------------
# Security rules
# ---------------------------------------------------------------------------

def rule_antivirus_disabled(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "security.antivirus_disabled")
    sec = (ctx.get("inventory") or {}).get("security") or (ctx.get("metrics") or {}).get("security") or {}
    t = RuleTrigger(rule_key="security.antivirus_disabled", title=pol["title"], category=pol["category"],
                    recommendation=pol.get("recommendation"))
    if not pol.get("enabled", True) or not isinstance(sec, dict) or not sec:
        return t
    av_enabled = sec.get("antivirus_enabled")
    if av_enabled is None:
        return t
    if av_enabled is False:
        t.triggered = True
        t.severity = pol["escalations"][0]["severity"]
        t.current_value = "disabled"
    else:
        t.clear = True
    return t


def rule_firewall_disabled(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "security.firewall_disabled")
    sec = (ctx.get("inventory") or {}).get("security") or (ctx.get("metrics") or {}).get("security") or {}
    t = RuleTrigger(rule_key="security.firewall_disabled", title=pol["title"], category=pol["category"],
                    recommendation=pol.get("recommendation"))
    if not pol.get("enabled", True) or not isinstance(sec, dict) or not sec:
        return t
    fw = sec.get("firewall_enabled")
    if fw is None:
        return t
    if fw is False:
        t.triggered = True
        t.severity = pol["escalations"][0]["severity"]
        t.current_value = "disabled"
    else:
        t.clear = True
    return t


def rule_updates_missing(ctx: dict[str, Any], policies: dict) -> list[RuleTrigger]:
    """Two distinct rules: critical vs non-critical updates missing."""
    inv = ctx.get("inventory") or {}
    upd = inv.get("updates") or inv.get("windows_updates") or {}
    results: list[RuleTrigger] = []

    pol_c = _policy(policies, "updates.missing.critical")
    t_c = RuleTrigger(rule_key="updates.missing.critical", title=pol_c["title"], category=pol_c["category"],
                      recommendation=pol_c.get("recommendation"))
    pol_n = _policy(policies, "updates.missing.noncritical")
    t_n = RuleTrigger(rule_key="updates.missing.noncritical", title=pol_n["title"], category=pol_n["category"],
                      recommendation=pol_n.get("recommendation"))

    if not isinstance(upd, dict) or not upd:
        return [t_c, t_n]  # nothing to say; do not clear (no data)
    critical = int(upd.get("pending_critical") or upd.get("critical") or 0)
    pending = int(upd.get("pending") or 0)
    if pol_c.get("enabled", True):
        if critical > 0:
            t_c.triggered = True
            t_c.severity = pol_c["escalations"][0]["severity"]
            t_c.current_value = critical
            t_c.unit = "critical updates"
        else:
            t_c.clear = True
    non_critical = max(0, pending - critical)
    if pol_n.get("enabled", True):
        if non_critical > 0:
            t_n.triggered = True
            t_n.severity = pol_n["escalations"][0]["severity"]
            t_n.current_value = non_critical
            t_n.unit = "updates"
        else:
            t_n.clear = True
    results.extend([t_c, t_n])
    return results


# ---------------------------------------------------------------------------
# Peripheral rules
# ---------------------------------------------------------------------------

def rule_usb_inserted(ctx: dict[str, Any], policies: dict) -> list[RuleTrigger]:
    """Emit a low-severity alert for each newly connected USB device.

    The engine identifies novelty by comparing against the previously stored
    ``inventory.usb.known_ids`` snapshot.
    """
    pol = _policy(policies, "usb.inserted")
    inv = ctx.get("inventory") or {}
    prev_inv = ctx.get("previous_inventory") or {}
    usb = ((inv.get("usb") or {}).get("devices")) or (inv.get("usb") if isinstance(inv.get("usb"), list) else None) or []
    prev_usb = ((prev_inv.get("usb") or {}).get("devices")) or (prev_inv.get("usb") if isinstance(prev_inv.get("usb"), list) else None) or []
    results: list[RuleTrigger] = []
    if not pol.get("enabled", True) or not isinstance(usb, list):
        return results
    prev_ids = {(d.get("id") or d.get("vid_pid") or d.get("serial") or d.get("name") or "") for d in prev_usb if isinstance(d, dict)}
    for d in usb:
        if not isinstance(d, dict):
            continue
        did = d.get("id") or d.get("vid_pid") or d.get("serial") or d.get("name") or ""
        if did and did in prev_ids:
            continue  # not new
        t = RuleTrigger(rule_key="usb.inserted", title=pol["title"], category=pol["category"],
                        recommendation=pol.get("recommendation"), triggered=True,
                        severity=pol["escalations"][0]["severity"],
                        current_value=d.get("name") or did or "USB device",
                        dimension_key=str(did or d.get("name") or "unknown"),
                        context={"device": d})
        results.append(t)
    return results


# ---------------------------------------------------------------------------
# Extended enterprise rules (best-effort: only fire when telemetry present).
# ---------------------------------------------------------------------------

def _pick_escalation_inverted(policy: dict[str, Any], value: float | None) -> dict[str, Any] | None:
    """Pick escalation where LOWER values are worse (e.g. disk health %, health score %).

    Walks escalations sorted by threshold DESC and returns the last one whose
    threshold the value has fallen below. This gives us
    ``value < 70 → medium; value < 20 → critical`` semantics with a single list.
    """
    if value is None:
        return None
    picked = None
    for esc in sorted(policy.get("escalations") or [], key=lambda e: -(e.get("threshold") or 0)):
        thr = esc.get("threshold")
        if thr is None or value <= thr:
            picked = esc
    return picked


def rule_ssd_failure_predicted(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "ssd.failure_predicted")
    metrics = ctx.get("metrics") or {}
    # Confidence % from an ML model; agent may attach this to a specific drive.
    v = _num(metrics.get("ssd_failure_confidence") or metrics.get("smart_failure_confidence"))
    t = RuleTrigger(rule_key="ssd.failure_predicted", title=pol["title"], category=pol["category"],
                    unit=pol.get("unit"), recommendation=pol.get("recommendation"),
                    current_value=v)
    if v is None or not pol.get("enabled", True):
        return t
    esc = _pick_escalation_by_value(pol, v)
    if esc is None:
        t.clear = True
        return t
    t.triggered = True
    t.severity = esc["severity"]
    t.threshold = esc.get("threshold")
    return t


def rule_disk_health(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "disk.health.low")
    m = ctx.get("metrics") or {}
    v = _num(m.get("disk_health_percent") or m.get("ssd_health_percent"))
    t = RuleTrigger(rule_key="disk.health.low", title=pol["title"], category=pol["category"],
                    unit=pol.get("unit"), recommendation=pol.get("recommendation"),
                    current_value=v)
    if v is None or not pol.get("enabled", True):
        return t
    esc = _pick_escalation_inverted(pol, v)
    if esc is None:
        t.clear = True
        return t
    t.triggered = True
    t.severity = esc["severity"]
    t.threshold = esc.get("threshold")
    return t


def rule_gpu_temperature(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "gpu.temperature.high")
    v = _num((ctx.get("metrics") or {}).get("gpu_temp_c"))
    t = RuleTrigger(rule_key="gpu.temperature.high", title=pol["title"], category=pol["category"],
                    unit=pol.get("unit"), recommendation=pol.get("recommendation"),
                    current_value=v)
    if v is None or v <= 0 or not pol.get("enabled", True):
        return t
    esc = _pick_escalation_by_value(pol, v)
    if esc is None:
        t.clear = True
        return t
    t.triggered = True
    t.severity = esc["severity"]
    t.threshold = esc.get("threshold")
    t.dwell_seconds = int(esc.get("dwell_seconds", 0))
    return t


def rule_battery_health(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "battery.health.low")
    m = ctx.get("metrics") or {}
    inv = ctx.get("inventory") or {}
    v = _num(m.get("battery_health_percent") or (inv.get("battery") or {}).get("health_percent"))
    t = RuleTrigger(rule_key="battery.health.low", title=pol["title"], category=pol["category"],
                    unit=pol.get("unit"), recommendation=pol.get("recommendation"),
                    current_value=v)
    if v is None or not pol.get("enabled", True):
        return t
    esc = _pick_escalation_inverted(pol, v)
    if esc is None:
        t.clear = True
        return t
    t.triggered = True
    t.severity = esc["severity"]
    t.threshold = esc.get("threshold")
    return t


def rule_fan_abnormal(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "fan.abnormal")
    m = ctx.get("metrics") or {}
    fans = m.get("fans") or (ctx.get("inventory") or {}).get("fans") or []
    t = RuleTrigger(rule_key="fan.abnormal", title=pol["title"], category=pol["category"],
                    recommendation=pol.get("recommendation"))
    if not pol.get("enabled", True) or not isinstance(fans, list) or not fans:
        return t
    abnormal = [f for f in fans if isinstance(f, dict)
                and (f.get("status") in ("abnormal", "warning", "failed")
                     or (f.get("rpm") is not None and f.get("rpm") == 0))]
    if not abnormal:
        t.clear = True
        return t
    t.triggered = True
    t.severity = pol["escalations"][0]["severity"]
    t.current_value = ", ".join([f.get("name") or "fan" for f in abnormal[:3]])
    t.dwell_seconds = int(pol["escalations"][0].get("dwell_seconds", 0))
    t.context = {"abnormal_fans": abnormal[:5]}
    return t


def rule_power_supply(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "power.supply.failure")
    m = ctx.get("metrics") or {}
    inv = ctx.get("inventory") or {}
    psu = m.get("power_supply") or inv.get("power_supply") or {}
    t = RuleTrigger(rule_key="power.supply.failure", title=pol["title"], category=pol["category"],
                    recommendation=pol.get("recommendation"))
    if not pol.get("enabled", True) or not isinstance(psu, dict) or not psu:
        return t
    status = str(psu.get("status") or "").lower()
    if status in ("failed", "fault", "critical"):
        t.triggered = True
        t.severity = pol["escalations"][0]["severity"]
        t.current_value = status
    elif status:
        t.clear = True
    return t


def rule_memory_leak(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "memory.leak")
    m = ctx.get("metrics") or {}
    detected = bool(m.get("memory_leak_detected"))
    t = RuleTrigger(rule_key="memory.leak", title=pol["title"], category=pol["category"],
                    recommendation=pol.get("recommendation"))
    if not pol.get("enabled", True):
        return t
    if detected:
        t.triggered = True
        t.severity = pol["escalations"][0]["severity"]
        t.current_value = m.get("memory_leak_process") or "unknown process"
        t.dwell_seconds = int(pol["escalations"][0].get("dwell_seconds", 0))
    else:
        t.clear = True
    return t


def rule_app_crashes(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "app.crashes.frequent")
    m = ctx.get("metrics") or {}
    v = _num(m.get("app_crashes_per_hour"))
    t = RuleTrigger(rule_key="app.crashes.frequent", title=pol["title"], category=pol["category"],
                    unit=pol.get("unit"), recommendation=pol.get("recommendation"),
                    current_value=v)
    if v is None or not pol.get("enabled", True):
        return t
    esc = _pick_escalation_by_value(pol, v)
    if esc is None:
        t.clear = True
        return t
    t.triggered = True
    t.severity = esc["severity"]
    t.threshold = esc.get("threshold")
    t.dwell_seconds = int(esc.get("dwell_seconds", 0))
    return t


def rule_login_failures(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "auth.login_failures")
    m = ctx.get("metrics") or {}
    v = _num(m.get("login_failures_last_5m"))
    t = RuleTrigger(rule_key="auth.login_failures", title=pol["title"], category=pol["category"],
                    unit=pol.get("unit"), recommendation=pol.get("recommendation"),
                    current_value=v)
    if v is None or not pol.get("enabled", True):
        return t
    esc = _pick_escalation_by_value(pol, v)
    if esc is None:
        t.clear = True
        return t
    t.triggered = True
    t.severity = esc["severity"]
    t.threshold = esc.get("threshold")
    return t


def rule_health_score(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    """Alert when the computed device health score drops.

    The engine writes ``health.score`` on the device doc; we read it from
    ``ctx['device']`` and use inverted-threshold semantics.
    """
    pol = _policy(policies, "health.score.low")
    device = ctx.get("device") or {}
    health = device.get("health") or {}
    v = _num(health.get("score"))
    t = RuleTrigger(rule_key="health.score.low", title=pol["title"], category=pol["category"],
                    unit=pol.get("unit"), recommendation=pol.get("recommendation"),
                    current_value=v)
    if v is None or not pol.get("enabled", True):
        return t
    esc = _pick_escalation_inverted(pol, v)
    if esc is None:
        t.clear = True
        return t
    t.triggered = True
    t.severity = esc["severity"]
    t.threshold = esc.get("threshold")
    return t


def rule_health_risk(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "health.risk.high")
    device = ctx.get("device") or {}
    health = device.get("health") or {}
    v = _num(health.get("failure_risk_percent"))
    t = RuleTrigger(rule_key="health.risk.high", title=pol["title"], category=pol["category"],
                    unit=pol.get("unit"), recommendation=pol.get("recommendation"),
                    current_value=v)
    if v is None or not pol.get("enabled", True):
        return t
    esc = _pick_escalation_by_value(pol, v)
    if esc is None:
        t.clear = True
        return t
    t.triggered = True
    t.severity = esc["severity"]
    t.threshold = esc.get("threshold")
    return t


def rule_system_restart(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    """Fire once when a fresh boot event is reported by the agent."""
    pol = _policy(policies, "system.restart")
    m = ctx.get("metrics") or {}
    boot_ts = m.get("boot_ts") or m.get("last_boot_ts")
    prev_boot_ts = ((ctx.get("previous_metrics") or {}).get("boot_ts")
                    or (ctx.get("previous_metrics") or {}).get("last_boot_ts"))
    t = RuleTrigger(rule_key="system.restart", title=pol["title"], category=pol["category"],
                    recommendation=pol.get("recommendation"))
    if not pol.get("enabled", True) or not boot_ts:
        return t
    if prev_boot_ts and boot_ts != prev_boot_ts:
        t.triggered = True
        t.severity = pol["escalations"][0]["severity"]
        t.current_value = str(boot_ts)
        t.dimension_key = str(boot_ts)  # unique per boot; won't dedup old restarts
    return t


def rule_agent_outdated(ctx: dict[str, Any], policies: dict) -> RuleTrigger:
    pol = _policy(policies, "agent.version_outdated")
    device = ctx.get("device") or {}
    v = device.get("agent_version")
    latest = ctx.get("latest_agent_version")
    t = RuleTrigger(rule_key="agent.version_outdated", title=pol["title"], category=pol["category"],
                    recommendation=pol.get("recommendation"))
    if not pol.get("enabled", True) or not v or not latest:
        return t
    if str(v) != str(latest):
        t.triggered = True
        t.severity = pol["escalations"][0]["severity"]
        t.current_value = f"{v} (latest {latest})"
    else:
        t.clear = True
    return t


def rule_peripheral_new(ctx: dict[str, Any], policies: dict) -> list[RuleTrigger]:
    """Emit a low-severity alert for each newly connected printer/monitor."""
    pol = _policy(policies, "peripheral.new_connected")
    inv = ctx.get("inventory") or {}
    prev_inv = ctx.get("previous_inventory") or {}
    results: list[RuleTrigger] = []
    if not pol.get("enabled", True):
        return results
    for kind in ("printers", "monitors"):
        cur = inv.get(kind) or []
        prev = prev_inv.get(kind) or []
        if not isinstance(cur, list):
            continue
        prev_ids = {(d.get("id") or d.get("name") or "") for d in prev if isinstance(d, dict)}
        for d in cur:
            if not isinstance(d, dict):
                continue
            did = d.get("id") or d.get("name") or ""
            if did and did in prev_ids:
                continue
            results.append(RuleTrigger(
                rule_key="peripheral.new_connected", title=pol["title"], category=pol["category"],
                recommendation=pol.get("recommendation"), triggered=True,
                severity=pol["escalations"][0]["severity"],
                current_value=f"{kind[:-1]}: {d.get('name') or did}",
                dimension_key=f"{kind}:{did or d.get('name') or 'unknown'}",
                context={"kind": kind[:-1], "device": d}))
    return results


def rule_software_new(ctx: dict[str, Any], policies: dict) -> list[RuleTrigger]:
    """Emit a low-severity alert for each newly installed application.

    Compares current inventory.software against previous_inventory.software.
    (This is orthogonal to the Software Policy engine which raises 'high'
    alerts for actual policy violations.)
    """
    pol = _policy(policies, "software.new_installed")
    inv = ctx.get("inventory") or {}
    prev_inv = ctx.get("previous_inventory") or {}
    results: list[RuleTrigger] = []
    if not pol.get("enabled", True):
        return results
    cur = inv.get("software") or []
    prev = prev_inv.get("software") or []
    if not isinstance(cur, list) or not isinstance(prev, list):
        return results
    prev_keys = {f"{(s.get('name') or '').lower()}|{s.get('version') or ''}"
                 for s in prev if isinstance(s, dict)}
    for s in cur:
        if not isinstance(s, dict):
            continue
        key = f"{(s.get('name') or '').lower()}|{s.get('version') or ''}"
        if not key.split("|")[0] or key in prev_keys:
            continue
        results.append(RuleTrigger(
            rule_key="software.new_installed", title=pol["title"], category=pol["category"],
            recommendation=pol.get("recommendation"), triggered=True,
            severity=pol["escalations"][0]["severity"],
            current_value=f"{s.get('name')} {s.get('version') or ''}".strip(),
            dimension_key=key,
            context={"software": s}))
    return results


# ---------------------------------------------------------------------------
# Master registry (rules that produce a single trigger per invocation).
# ---------------------------------------------------------------------------
SingleRule = Callable[[dict, dict], RuleTrigger]
MultiRule = Callable[[dict, dict], list[RuleTrigger]]

SINGLE_RULES: list[SingleRule] = [
    rule_cpu_high,
    rule_ram_high,
    rule_temperature_high,
    rule_disk_low,
    rule_ssd_failure,
    rule_ssd_failure_predicted,
    rule_disk_health,
    rule_gpu_temperature,
    rule_battery_health,
    rule_fan_abnormal,
    rule_power_supply,
    rule_memory_leak,
    rule_app_crashes,
    rule_login_failures,
    rule_health_score,
    rule_health_risk,
    rule_system_restart,
    rule_agent_outdated,
    rule_offline,
    rule_network_failure,
    rule_antivirus_disabled,
    rule_firewall_disabled,
]

MULTI_RULES: list[MultiRule] = [
    rule_updates_missing,
    rule_usb_inserted,
    rule_peripheral_new,
    rule_software_new,
]
