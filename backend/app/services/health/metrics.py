"""Metric evaluators for the V1 rule-based health engine.

Each evaluator receives the full device context and returns a
``MetricEvaluation``. Evaluators MUST:

  * Return ``evaluated=False`` and ``deduction=0.0`` when the underlying
    signal is unavailable (missing sensor, no data yet, unsupported OS).
  * Include a ``reason`` and ``recommendation`` whenever they deduct points.
  * Keep the deduction bounded by the metric's ``weight``.

The registry (V1 engine) will sum weights of evaluated metrics to compute
**data completeness**. Weights of missing metrics are NOT redistributed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .contracts import MetricEvaluation, Severity

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _severity_from_ratio(ratio: float) -> Severity:
    """Map a deduction ratio (0..1 of weight) to a severity label."""
    if ratio <= 0:
        return "ok"
    if ratio < 0.25:
        return "low"
    if ratio < 0.5:
        return "medium"
    if ratio < 0.8:
        return "high"
    return "critical"


def _parse_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# Individual evaluators
# ---------------------------------------------------------------------------

def eval_cpu_usage(ctx: dict[str, Any]) -> MetricEvaluation:
    w = 8
    m = ctx.get("metrics") or {}
    v = _num(m.get("cpu_percent"))
    ev = MetricEvaluation(key="cpu_usage", label="CPU Usage", category="performance",
                          weight=w, unit="%", normal_range="0–75%")
    if v is None:
        return ev
    ev.evaluated = True
    ev.current_value = round(v, 1)
    if v < 60:
        ev.severity = "ok"
        return ev
    # Linear ramp from 60% (0 deduction) to 100% (full weight)
    ded = _clamp((v - 60.0) / 40.0, 0.0, 1.0) * w
    ev.deduction = round(ded, 2)
    ev.severity = _severity_from_ratio(ded / w)
    if v >= 90:
        ev.reason = f"Sustained high CPU load: current usage {v:.0f}% (normal ≤75%)."
        ev.recommendation = "Investigate top processes and terminate runaway tasks; consider scheduling heavy jobs off-peak."
    elif v >= 75:
        ev.reason = f"Elevated CPU usage: {v:.0f}% (normal ≤75%)."
        ev.recommendation = "Review scheduled tasks and background scanners; profile heavy processes."
    else:
        ev.reason = f"CPU trending up: {v:.0f}%."
        ev.recommendation = "Monitor for sustained load over the next hour."
    return ev


def eval_cpu_temperature(ctx: dict[str, Any]) -> MetricEvaluation:
    w = 12
    m = ctx.get("metrics") or {}
    v = _num(m.get("cpu_temp_c"))
    ev = MetricEvaluation(key="cpu_temperature", label="CPU Temperature", category="thermal",
                          weight=w, unit="°C", normal_range="40–75 °C")
    if v is None or v <= 0:
        return ev
    ev.evaluated = True
    ev.current_value = round(v, 1)
    if v < 75:
        ev.severity = "ok"
        return ev
    # 75 → 0 deduction; 95 → full weight
    ded = _clamp((v - 75.0) / 20.0, 0.0, 1.0) * w
    ev.deduction = round(ded, 2)
    ev.severity = _severity_from_ratio(ded / w)
    if v >= 90:
        ev.reason = f"Thermal throttling likely: CPU at {v:.0f}°C (normal 40–75°C)."
        ev.recommendation = "Immediately reduce load, clean fans/vents, inspect thermal paste and airflow."
    elif v >= 85:
        ev.reason = f"Elevated CPU temperature: {v:.0f}°C."
        ev.recommendation = "Clean cooling fan and inspect thermal paste; verify case ventilation is unobstructed."
    else:
        ev.reason = f"Warm CPU: {v:.0f}°C."
        ev.recommendation = "Ensure the device has clearance for airflow; consider cleaning intake vents."
    return ev


def eval_ram_usage(ctx: dict[str, Any]) -> MetricEvaluation:
    w = 8
    m = ctx.get("metrics") or {}
    v = _num(m.get("ram_percent"))
    ev = MetricEvaluation(key="ram_usage", label="RAM Usage", category="performance",
                          weight=w, unit="%", normal_range="0–80%")
    if v is None:
        return ev
    ev.evaluated = True
    ev.current_value = round(v, 1)
    if v < 65:
        ev.severity = "ok"
        return ev
    ded = _clamp((v - 65.0) / 35.0, 0.0, 1.0) * w
    ev.deduction = round(ded, 2)
    ev.severity = _severity_from_ratio(ded / w)
    if v >= 90:
        ev.reason = f"Memory pressure: RAM at {v:.0f}% (normal ≤80%)."
        ev.recommendation = "Close heavy applications; plan a RAM upgrade if this persists."
    elif v >= 80:
        ev.reason = f"High RAM usage: {v:.0f}%."
        ev.recommendation = "Identify memory-heavy processes; check for memory leaks in long-running apps."
    else:
        ev.reason = f"RAM trending up: {v:.0f}%."
        ev.recommendation = "Monitor over the next telemetry cycles."
    return ev


def eval_disk_usage(ctx: dict[str, Any]) -> MetricEvaluation:
    w = 8
    m = ctx.get("metrics") or {}
    v = _num(m.get("disk_percent"))
    ev = MetricEvaluation(key="disk_usage", label="Disk Usage", category="storage",
                          weight=w, unit="%", normal_range="0–80% used")
    if v is None:
        return ev
    ev.evaluated = True
    ev.current_value = round(v, 1)
    if v < 70:
        ev.severity = "ok"
        return ev
    ded = _clamp((v - 70.0) / 30.0, 0.0, 1.0) * w
    ev.deduction = round(ded, 2)
    ev.severity = _severity_from_ratio(ded / w)
    if v >= 95:
        ev.reason = f"Disk almost full: {v:.0f}% used."
        ev.recommendation = "Free space urgently: clear temp files, remove unused apps, expand the volume."
    elif v >= 85:
        ev.reason = f"Disk high usage: {v:.0f}% used."
        ev.recommendation = "Plan a cleanup and consider archiving cold data."
    else:
        ev.reason = f"Disk usage rising: {v:.0f}%."
        ev.recommendation = "Schedule cleanup within the week."
    return ev


def eval_ssd_health(ctx: dict[str, Any]) -> MetricEvaluation:
    w = 12
    m = ctx.get("metrics") or {}
    inv = ctx.get("inventory") or {}
    smart = m.get("smart") or ((inv.get("disk") or {}).get("smart")) or []
    ev = MetricEvaluation(key="ssd_health", label="SSD / Disk Health (SMART)", category="storage",
                          weight=w, unit="assessment", normal_range="PASS on every drive")
    if not isinstance(smart, list) or not smart:
        return ev
    ev.evaluated = True
    total = len(smart)
    failing = [d for d in smart if isinstance(d, dict) and (d.get("assessment") or "").upper() not in ("PASS", "OK", "") ]
    unknown = [d for d in smart if isinstance(d, dict) and not d.get("assessment")]
    ev.current_value = f"{total - len(failing)} PASS / {total} drives"
    if not failing:
        ev.severity = "ok"
        if unknown:
            ev.reason = f"{len(unknown)}/{total} drive(s) reported no SMART assessment."
            ev.recommendation = "Install smartctl or verify SMART is enabled in BIOS for full visibility."
        return ev
    ratio = len(failing) / max(1, total)
    ded = ratio * w
    ev.deduction = round(ded, 2)
    ev.severity = "critical" if ratio >= 0.5 else "high"
    names = ", ".join([d.get("name") or d.get("model") or "drive" for d in failing[:3]])
    ev.reason = f"SMART reports failure on {len(failing)}/{total} drive(s) ({names})."
    ev.recommendation = "Back up critical data immediately and replace failing drive(s) before catastrophic loss."
    return ev


def eval_network_health(ctx: dict[str, Any]) -> MetricEvaluation:
    w = 8
    m = ctx.get("metrics") or {}
    latency = _num(m.get("latency_ms"))
    pkt_errs = _num(m.get("packet_errors"))
    adapters = m.get("adapters") or []
    ev = MetricEvaluation(key="network_health", label="Network Health", category="network",
                          weight=w, unit="ms latency", normal_range="latency <100 ms, no adapter errors")
    has_signal = latency is not None or pkt_errs is not None or isinstance(adapters, list) and adapters
    if not has_signal:
        return ev
    ev.evaluated = True
    ded = 0.0
    reasons: list[str] = []
    if latency is not None:
        ev.current_value = f"{latency:.0f} ms"
        if latency >= 100:
            portion = _clamp((latency - 100.0) / 400.0, 0.0, 1.0) * (w * 0.5)
            ded += portion
            reasons.append(f"latency {latency:.0f} ms (normal <100 ms)")
    up_adapters = [a for a in adapters if isinstance(a, dict) and a.get("is_up")]
    if adapters and not up_adapters:
        ded += w * 0.5
        reasons.append("no network adapter is up")
    if pkt_errs is not None and pkt_errs > 0:
        ded += min(w * 0.25, pkt_errs / 1000.0)
        reasons.append(f"{int(pkt_errs)} packet errors observed")
    ded = round(_clamp(ded, 0.0, w), 2)
    ev.deduction = ded
    ev.severity = _severity_from_ratio(ded / w)
    if ded > 0:
        ev.reason = "Network degradation: " + "; ".join(reasons) + "."
        ev.recommendation = "Check cabling / Wi-Fi signal, restart the network adapter, verify DNS/gateway."
    return ev


def eval_offline_frequency(ctx: dict[str, Any]) -> MetricEvaluation:
    w = 8
    device = ctx.get("device") or {}
    last_seen = _parse_iso(device.get("last_seen"))
    is_online = bool(device.get("is_online"))
    ev = MetricEvaluation(key="offline_frequency", label="Offline Frequency", category="availability",
                          weight=w, unit="minutes offline", normal_range="online, seen <5 min ago")
    if last_seen is None:
        return ev
    ev.evaluated = True
    now = datetime.now(timezone.utc)
    minutes_since = (now - last_seen).total_seconds() / 60.0
    ev.current_value = f"{minutes_since:.1f} min since last check-in" if not is_online else "online"
    if is_online and minutes_since < 5:
        ev.severity = "ok"
        return ev
    # 5 min → light; 60 min → full weight
    ded = _clamp((minutes_since - 5.0) / 55.0, 0.0, 1.0) * w
    ev.deduction = round(ded, 2)
    ev.severity = _severity_from_ratio(ded / w)
    if minutes_since > 60:
        ev.reason = f"Device has been offline for {minutes_since:.0f} minutes."
        ev.recommendation = "Verify power, network connectivity, and that the DigitalTwinAgent service is running."
    else:
        ev.reason = f"Device last checked in {minutes_since:.1f} minutes ago."
        ev.recommendation = "Investigate intermittent connectivity or scheduled sleep policies."
    return ev


def eval_crash_frequency(ctx: dict[str, Any]) -> MetricEvaluation:
    w = 10
    inv = ctx.get("inventory") or {}
    events = (inv.get("events") or {}).get("events") or []
    recent_alerts = ctx.get("recent_alerts") or []
    ch = inv.get("crash_history") or {}
    ev = MetricEvaluation(key="crash_frequency", label="Crash Frequency", category="stability",
                          weight=w, unit="errors / 24h", normal_range="0 BSODs / ≤2 app-errors in 24h")
    has_events = isinstance(events, list) and len(events) > 0
    has_alerts = isinstance(recent_alerts, list)
    has_ch = isinstance(ch, dict) and ch and (ch.get("supported") is not False)
    if not has_events and not has_alerts and not has_ch:
        return ev
    ev.evaluated = True
    error_events = [e for e in events if isinstance(e, dict) and (e.get("level") == "error")]
    crash_alerts = [a for a in recent_alerts if isinstance(a, dict) and (a.get("kind") or "").startswith("crash")]
    # Prefer the richer crash_history collector when present.
    bsod   = int(ch.get("bsod_count_7d")     or 0)
    hard   = int(ch.get("hard_reboot_7d")    or 0)
    appcr  = int(ch.get("app_crash_7d")      or 0)
    total_errors = bsod + hard + appcr if has_ch else (len(error_events) + len(crash_alerts))
    ev.current_value = (
        f"BSOD={bsod} hard-reboots={hard} app-crashes={appcr}"
        if has_ch else f"{total_errors} error events / 24h"
    )
    # BSODs are disproportionately bad.
    ded = 0.0
    reasons: list[str] = []
    if bsod:
        ded += min(w, bsod * 5.0);  reasons.append(f"{bsod} BSOD(s) in 7d")
    if hard:
        ded += min(w * 0.4, hard * 1.5); reasons.append(f"{hard} unexpected reboot(s) in 7d")
    if appcr > 2:
        ded += min(w * 0.4, (appcr - 2) * 0.4); reasons.append(f"{appcr} app crashes in 7d")
    if not has_ch and total_errors > 2:
        ded = _clamp((total_errors - 2) / 13.0, 0.0, 1.0) * w
        reasons.append(f"{total_errors} error events in the recent window")
    ded = round(_clamp(ded, 0.0, w), 2)
    ev.deduction = ded
    if ded == 0:
        ev.severity = "ok"; return ev
    ev.severity = _severity_from_ratio(ded / w)
    ev.reason = "Stability issues: " + ", ".join(reasons) + "."
    ev.recommendation = "Investigate minidumps + Kernel-Power 41 events; check drivers and PSU health."
    return ev


def eval_security_status(ctx: dict[str, Any]) -> MetricEvaluation:
    w = 10
    inv = ctx.get("inventory") or {}
    m = ctx.get("metrics") or {}
    # NEW shape (Phase-8 SecurityPostureCollector) takes precedence.
    posture = inv.get("security_posture") or {}
    legacy_sec = inv.get("security") or m.get("security") or {}
    ev = MetricEvaluation(key="security_status", label="Security (Firewall / AV / Defender / BitLocker / TPM / SecureBoot)",
                          category="security", weight=w, unit="status",
                          normal_range="Firewall ON · AV enabled · Defender fresh · BitLocker + TPM + SecureBoot on")
    if not isinstance(posture, dict) or not posture:
        # Fall back to legacy flat shape.
        sec = legacy_sec
        if not isinstance(sec, dict) or not sec:
            return ev
        ev.evaluated = True
        firewall = sec.get("firewall_enabled")
        av = sec.get("antivirus_enabled")
        defender = sec.get("defender_enabled")
        signatures = sec.get("defender_signatures_up_to_date", sec.get("signatures_up_to_date"))
        issues: list[str] = []
        ded = 0.0
        if firewall is False:
            issues.append("firewall disabled"); ded += w * 0.4
        if av is False:
            issues.append("antivirus disabled"); ded += w * 0.4
        if defender is False:
            issues.append("Defender disabled"); ded += w * 0.3
        if signatures is False:
            issues.append("virus signatures out of date"); ded += w * 0.2
        ded = round(_clamp(ded, 0.0, w), 2)
        ev.deduction = ded
        ev.current_value = "; ".join([f"firewall={firewall}", f"AV={av}", f"defender={defender}"])
        if ded == 0:
            ev.severity = "ok"; return ev
        ev.severity = _severity_from_ratio(ded / w)
        ev.reason = "Security posture weakened: " + ", ".join(issues) + "."
        ev.recommendation = "Re-enable disabled protections and update virus signatures."
        return ev

    # ---- Rich posture flow ----
    ev.evaluated = True
    fw     = posture.get("firewall") or {}
    dfd    = posture.get("windows_defender") or {}
    bl     = posture.get("bitlocker") or {}
    sb     = posture.get("secure_boot") or {}
    tpm    = posture.get("tpm") or {}
    av_any = (posture.get("antivirus") or {}).get("any_enabled")
    posture_score = posture.get("posture_score")

    issues: list[str] = []
    ded = 0.0
    if av_any is False:
        issues.append("no antivirus enabled"); ded += w * 0.35
    if dfd.get("rtp_enabled") is False:
        issues.append("Defender real-time protection off"); ded += w * 0.25
    sig_age = dfd.get("signatures_age_days")
    if isinstance(sig_age, (int, float)) and sig_age > 7:
        issues.append(f"AV signatures {int(sig_age)} days stale"); ded += w * 0.15
    if fw.get("any_disabled") is True:
        issues.append("Windows Firewall disabled on ≥1 profile"); ded += w * 0.15
    if bl.get("available") and not bl.get("all_volumes_protected"):
        issues.append("BitLocker not enabled on all volumes"); ded += w * 0.10
    if sb.get("available") and sb.get("enabled") is False:
        issues.append("Secure Boot disabled"); ded += w * 0.10
    if tpm.get("present") is False:
        issues.append("no TPM present"); ded += w * 0.05
    elif tpm.get("activated") is False:
        issues.append("TPM present but not activated"); ded += w * 0.05

    ded = round(_clamp(ded, 0.0, w), 2)
    ev.deduction = ded
    ev.current_value = (
        f"score={posture_score}  fw={not fw.get('any_disabled', True)} "
        f"defender_rtp={dfd.get('rtp_enabled')} bitlocker={bl.get('all_volumes_protected')} "
        f"tpm={tpm.get('activated')} secureboot={sb.get('enabled')}"
    )
    if ded == 0:
        ev.severity = "ok"; return ev
    ev.severity = _severity_from_ratio(ded / w)
    ev.reason = "Security posture weakened: " + ", ".join(issues) + "."
    ev.recommendation = "Restore protections in Windows Security → Device security / Virus & threat protection."
    return ev


def eval_windows_updates(ctx: dict[str, Any]) -> MetricEvaluation:
    w = 6
    inv = ctx.get("inventory") or {}
    upd = inv.get("windows_updates") or inv.get("updates") or {}
    ev = MetricEvaluation(key="windows_updates", label="Operating System Updates", category="security",
                          weight=w, unit="pending", normal_range="0 pending critical updates")
    if not isinstance(upd, dict) or not upd or upd.get("supported") is False:
        return ev
    ev.evaluated = True
    # Accept BOTH the new (pending_count / critical_pending_count) and legacy
    # (pending / pending_critical) field names.
    pending = int(upd.get("pending_count") or upd.get("pending") or 0)
    critical = int(upd.get("critical_pending_count") or upd.get("pending_critical") or upd.get("critical") or 0)
    reboot = bool(upd.get("reboot_required"))
    ev.current_value = f"{pending} pending ({critical} critical){' - reboot required' if reboot else ''}"
    ded = 0.0
    reasons: list[str] = []
    if critical > 0:
        ded += min(w * 0.7, critical * (w * 0.15))
        reasons.append(f"{critical} critical update(s) pending")
    if pending > critical:
        ded += min(w * 0.3, (pending - critical) * (w * 0.05))
        reasons.append(f"{pending - critical} non-critical update(s) pending")
    if reboot:
        ded += w * 0.2
        reasons.append("pending reboot to finish install")
    ded = round(_clamp(ded, 0.0, w), 2)
    ev.deduction = ded
    if ded == 0:
        ev.severity = "ok"
        return ev
    ev.severity = _severity_from_ratio(ded / w)
    ev.reason = "OS updates outstanding: " + ", ".join(reasons) + "."
    ev.recommendation = "Schedule a maintenance window to install pending updates and reboot."
    return ev


def eval_fan_health(ctx: dict[str, Any]) -> MetricEvaluation:
    w = 4
    m = ctx.get("metrics") or {}
    inv = ctx.get("inventory") or {}
    fans = m.get("fans") or ((inv.get("fans_temps") or {}).get("fans")) or []
    ev = MetricEvaluation(key="fan_health", label="Fan Health", category="thermal",
                          weight=w, unit="RPM", normal_range="all fans reporting >300 RPM")
    if not isinstance(fans, list) or not fans:
        return ev
    ev.evaluated = True
    stalled = [f for f in fans if isinstance(f, dict) and _num(f.get("rpm")) is not None and _num(f.get("rpm")) < 300]
    reporting = [f for f in fans if isinstance(f, dict) and _num(f.get("rpm")) is not None]
    ev.current_value = f"{len(reporting)} fan(s) reporting, {len(stalled)} stalled"
    if not stalled:
        ev.severity = "ok"
        return ev
    ratio = len(stalled) / max(1, len(reporting) or 1)
    ded = round(_clamp(ratio, 0.0, 1.0) * w, 2)
    ev.deduction = ded
    ev.severity = _severity_from_ratio(ded / w)
    ev.reason = f"{len(stalled)} fan(s) below the safe RPM threshold."
    ev.recommendation = "Inspect cooling: dust build-up, seized bearings, or a disconnected fan header."
    return ev


def eval_battery_health(ctx: dict[str, Any]) -> MetricEvaluation:
    w = 4
    m = ctx.get("metrics") or {}
    inv = ctx.get("inventory") or {}
    battery = m.get("battery") or inv.get("battery") or {}
    ev = MetricEvaluation(key="battery_health", label="Battery Health", category="hardware",
                          weight=w, unit="health / charge", normal_range="health >70%, above 20% charge")
    if not isinstance(battery, dict) or not battery:
        return ev
    if battery.get("has_battery") is False:
        # Explicitly reported "no battery" → not evaluated (desktop / server)
        return ev
    ev.evaluated = True
    percent = _num(battery.get("percent"))
    health = _num(battery.get("health_percent"))
    plugged = battery.get("plugged")
    ev.current_value = (
        f"{percent:.0f}% charge" if percent is not None else "charge unknown"
    ) + (f", health {health:.0f}%" if health is not None else "")
    ded = 0.0
    reasons: list[str] = []
    if health is not None and health < 70:
        ded += _clamp((70 - health) / 70.0, 0.0, 1.0) * (w * 0.7)
        reasons.append(f"battery health at {health:.0f}% (below 70%)")
    if percent is not None and percent < 20 and not plugged:
        ded += w * 0.3
        reasons.append(f"low charge {percent:.0f}% on battery")
    ded = round(_clamp(ded, 0.0, w), 2)
    ev.deduction = ded
    if ded == 0:
        ev.severity = "ok"
        return ev
    ev.severity = _severity_from_ratio(ded / w)
    ev.reason = "Battery concerns: " + ", ".join(reasons) + "."
    ev.recommendation = "Replace an aging battery pack; keep the device plugged in when possible."
    return ev


def eval_services_health(ctx: dict[str, Any]) -> MetricEvaluation:
    w = 2
    inv = ctx.get("inventory") or {}
    services = (inv.get("services") or {}).get("services") or (inv.get("services") if isinstance(inv.get("services"), list) else None)
    ev = MetricEvaluation(key="services_health", label="Critical System Services", category="stability",
                          weight=w, unit="services", normal_range="critical services running")
    if not isinstance(services, list) or not services:
        return ev
    ev.evaluated = True
    critical_names = {"wuauserv", "windefend", "mpssvc", "eventlog", "schedule", "lsass", "cryptsvc"}
    stopped_critical = []
    for s in services:
        if not isinstance(s, dict):
            continue
        name = (s.get("name") or "").lower()
        status = (s.get("status") or s.get("active") or "").lower()
        if name in critical_names and status not in ("running", "active"):
            stopped_critical.append(name)
    ev.current_value = f"{len(stopped_critical)} critical services stopped"
    if not stopped_critical:
        ev.severity = "ok"
        return ev
    ratio = min(1.0, len(stopped_critical) / 3.0)
    ded = round(ratio * w, 2)
    ev.deduction = ded
    ev.severity = _severity_from_ratio(ded / w)
    ev.reason = "Critical services not running: " + ", ".join(stopped_critical) + "."
    ev.recommendation = "Restart the affected services and investigate why they stopped."
    return ev


def eval_display_health(ctx: dict[str, Any]) -> MetricEvaluation:
    """Display health -- flags disconnected panels / stuck resolution.

    Signals we look at (populated by MonitorsCollector):
      * ``inv['monitors']['monitors']`` -- list of {'name','width','height','connected'}
      * A monitor with ``connected=False`` or with resolution 0x0 is flagged
      * A "no monitors reported" state is *not* penalized (headless kiosks
        and RDP-only hosts are legit)
    """
    w = 3
    inv = ctx.get("inventory") or {}
    m_root = inv.get("monitors") or {}
    monitors = m_root.get("monitors") or m_root.get("displays") or []
    ev = MetricEvaluation(key="display_health", label="Display", category="peripherals",
                          weight=w, unit="status",
                          normal_range="all attached panels connected & reporting a valid resolution")
    if not isinstance(monitors, list) or not monitors:
        return ev
    ev.evaluated = True
    connected = [m for m in monitors if isinstance(m, dict) and m.get("connected") is not False]
    stuck = [
        m for m in connected
        if (_num(m.get("width")) in (None, 0)) or (_num(m.get("height")) in (None, 0))
    ]
    disconnected = [m for m in monitors if isinstance(m, dict) and m.get("connected") is False]
    ev.current_value = (
        f"{len(monitors)} panel(s), {len(disconnected)} disconnected, {len(stuck)} stuck"
    )
    if not disconnected and not stuck:
        ev.severity = "ok"
        return ev
    ded = 0.0
    reasons: list[str] = []
    if disconnected:
        ded += min(w * 0.6, len(disconnected) * w * 0.3)
        reasons.append(f"{len(disconnected)} panel(s) disconnected")
    if stuck:
        ded += min(w * 0.4, len(stuck) * w * 0.2)
        reasons.append(f"{len(stuck)} panel(s) reporting invalid resolution")
    ded = round(_clamp(ded, 0.0, w), 2)
    ev.deduction = ded
    ev.severity = _severity_from_ratio(ded / w)
    ev.reason = "Display issues: " + ", ".join(reasons) + "."
    ev.recommendation = "Check cables, dock connections, or GPU driver install state."
    return ev


# Ordered evaluator table (matches the product's fixed weight allocation).
Evaluator = Callable[[dict[str, Any]], MetricEvaluation]
EVALUATORS: list[Evaluator] = [
    eval_cpu_usage,
    eval_cpu_temperature,
    eval_ram_usage,
    eval_disk_usage,
    eval_ssd_health,
    eval_network_health,
    eval_offline_frequency,
    eval_crash_frequency,
    eval_security_status,
    eval_windows_updates,
    eval_fan_health,
    eval_battery_health,
    eval_services_health,
    eval_display_health,
]


def total_weight() -> int:
    """Returns 100 for the current allocation (kept computed for safety)."""
    return sum(_eval_dummy_weight(fn) for fn in EVALUATORS)


def _eval_dummy_weight(fn: Evaluator) -> int:
    # Run against an empty context to discover the metric's declared weight.
    return fn({}).weight
