"""Feature extraction for the prediction engine.

Turns a device context (telemetry + inventory + timeline) into a numeric
feature vector consumed by both rule-based scoring and the sklearn models.

Design notes
------------
* Every failure type has its own feature set; keeping them small (5-8 features)
  keeps the models interpretable and fast to fit even with tiny synthetic
  training data.
* Missing values fall back to a neutral default so we never spuriously trigger
  a prediction from the absence of data. The ``coverage`` counter tracks how
  many features had real data — the caller uses this to compute ``confidence``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _num(v: Any, default: float = 0.0) -> tuple[float, bool]:
    """Return (value, had_data). ``had_data`` is False if the input was missing."""
    if v is None:
        return default, False
    try:
        f = float(v)
        if f != f:  # NaN
            return default, False
        return f, True
    except (TypeError, ValueError):
        return default, False


def _timeline_slope(timeline: list[dict], key: str = "score") -> float:
    """Simple linear slope of the last N points. Negative = declining."""
    pts = [t.get(key) for t in (timeline or []) if isinstance(t.get(key), (int, float))]
    if len(pts) < 2:
        return 0.0
    n = len(pts)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(pts) / n
    num = sum((xs[i] - mean_x) * (pts[i] - mean_y) for i in range(n))
    den = sum((x - mean_x) ** 2 for x in xs) or 1.0
    return num / den


def _minutes_since(ts_str: str | None) -> float:
    if not ts_str:
        return 0.0
    try:
        dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 60.0)


# ---------------------------------------------------------------------------
# Feature builders (one per failure type).
# Return: (feature_vector, coverage_ratio, raw_dict_for_explainability)
# ---------------------------------------------------------------------------

def features_ssd(ctx: dict[str, Any]) -> tuple[list[float], float, dict[str, Any]]:
    m = ctx.get("metrics") or {}
    inv = ctx.get("inventory") or {}
    smart = m.get("smart") or (inv.get("disk") or {}).get("smart") or []
    # SMART assessment: 1 if any failing drive is flagged; 0 otherwise.
    smart_fail = 1.0 if any(
        isinstance(d, dict) and (d.get("assessment") or "").upper() not in ("PASS", "OK", "")
        for d in smart
    ) else 0.0
    reallocated = 0.0
    reallocated_had = False
    pending_sectors = 0.0
    pending_had = False
    for d in smart or []:
        if isinstance(d, dict):
            r, rh = _num(d.get("reallocated_sectors"))
            p, ph = _num(d.get("pending_sectors"))
            reallocated = max(reallocated, r)
            reallocated_had = reallocated_had or rh
            pending_sectors = max(pending_sectors, p)
            pending_had = pending_had or ph

    health_pct, hp_had = _num(m.get("ssd_health_percent") or m.get("disk_health_percent"), 100.0)
    disk_pct, dp_had = _num(m.get("disk_percent"))
    conf, conf_had = _num(m.get("ssd_failure_confidence"))
    temp, temp_had = _num(m.get("disk_temp_c"))

    feats = [smart_fail, reallocated, pending_sectors, 100.0 - health_pct, disk_pct, conf, temp]
    had = [True, reallocated_had, pending_had, hp_had, dp_had, conf_had, temp_had]
    coverage = sum(1 for h in had if h) / len(had)
    raw = {
        "smart_failing": bool(smart_fail),
        "reallocated_sectors": reallocated if reallocated_had else None,
        "pending_sectors": pending_sectors if pending_had else None,
        "disk_health_percent": health_pct if hp_had else None,
        "disk_percent": disk_pct if dp_had else None,
        "ssd_failure_confidence": conf if conf_had else None,
        "disk_temp_c": temp if temp_had else None,
    }
    return feats, coverage, raw


def features_fan(ctx: dict[str, Any]) -> tuple[list[float], float, dict[str, Any]]:
    m = ctx.get("metrics") or {}
    inv = ctx.get("inventory") or {}
    fans = m.get("fans") or inv.get("fans") or []
    fan_zero = 1.0 if any(isinstance(f, dict) and f.get("rpm") == 0 for f in fans) else 0.0
    abnormal = 1.0 if any(
        isinstance(f, dict) and str(f.get("status") or "").lower() in ("abnormal", "warning", "failed")
        for f in fans
    ) else 0.0
    cpu_temp, tc_had = _num(m.get("cpu_temp_c"))
    gpu_temp, tg_had = _num(m.get("gpu_temp_c"))
    max_rpm, rpm_had = 0.0, False
    for f in fans:
        if isinstance(f, dict):
            v, h = _num(f.get("rpm"))
            max_rpm = max(max_rpm, v)
            rpm_had = rpm_had or h
    has_data = bool(fans)
    feats = [fan_zero, abnormal, cpu_temp, gpu_temp, max_rpm]
    had = [has_data, has_data, tc_had, tg_had, rpm_had]
    coverage = sum(1 for h in had if h) / len(had)
    raw = {
        "fan_zero_rpm": bool(fan_zero),
        "fan_abnormal_status": bool(abnormal),
        "cpu_temp_c": cpu_temp if tc_had else None,
        "gpu_temp_c": gpu_temp if tg_had else None,
        "max_fan_rpm": max_rpm if rpm_had else None,
    }
    return feats, coverage, raw


def features_cpu_thermal(ctx: dict[str, Any]) -> tuple[list[float], float, dict[str, Any]]:
    m = ctx.get("metrics") or {}
    cpu_temp, tc_had = _num(m.get("cpu_temp_c"))
    cpu_pct, cp_had = _num(m.get("cpu_percent"))
    throttling = 1.0 if m.get("thermal_throttling") else 0.0
    tt_had = "thermal_throttling" in m
    # Rate of change from the timeline (if temp is stored)
    tl = ctx.get("recent_telemetry") or []
    temps = [t.get("metrics", {}).get("cpu_temp_c") for t in tl
             if isinstance(t, dict) and isinstance(t.get("metrics", {}).get("cpu_temp_c"), (int, float))]
    temp_slope = 0.0
    if len(temps) >= 2:
        temp_slope = (temps[-1] - temps[0]) / max(1, len(temps) - 1)
    feats = [cpu_temp, cpu_pct, throttling, temp_slope]
    had = [tc_had, cp_had, tt_had, len(temps) >= 2]
    coverage = sum(1 for h in had if h) / len(had)
    raw = {
        "cpu_temp_c": cpu_temp if tc_had else None,
        "cpu_percent": cpu_pct if cp_had else None,
        "thermal_throttling": bool(throttling) if tt_had else None,
        "cpu_temp_slope_per_sample": temp_slope,
    }
    return feats, coverage, raw


def features_battery(ctx: dict[str, Any]) -> tuple[list[float], float, dict[str, Any]]:
    m = ctx.get("metrics") or {}
    inv = ctx.get("inventory") or {}
    b = m.get("battery") or inv.get("battery") or {}
    if not isinstance(b, dict):
        b = {}
    health_pct, hp_had = _num(b.get("health_percent") or m.get("battery_health_percent"), 100.0)
    cycles, cy_had = _num(b.get("cycle_count"))
    design_cap, dc_had = _num(b.get("design_capacity"))
    full_cap, fc_had = _num(b.get("full_charge_capacity"))
    cap_ratio = (full_cap / design_cap * 100.0) if (fc_had and dc_had and design_cap > 0) else health_pct
    feats = [100.0 - health_pct, cycles, 100.0 - cap_ratio]
    had = [hp_had, cy_had, fc_had and dc_had]
    coverage = sum(1 for h in had if h) / len(had)
    raw = {
        "battery_health_percent": health_pct if hp_had else None,
        "cycle_count": cycles if cy_had else None,
        "capacity_ratio_percent": cap_ratio if (fc_had and dc_had) else None,
    }
    return feats, coverage, raw


def features_memory(ctx: dict[str, Any]) -> tuple[list[float], float, dict[str, Any]]:
    m = ctx.get("metrics") or {}
    ram_pct, r_had = _num(m.get("ram_percent"))
    leak = 1.0 if m.get("memory_leak_detected") else 0.0
    leak_had = "memory_leak_detected" in m
    ecc_errors, ecc_had = _num(m.get("ecc_errors"))
    swap_pct, sw_had = _num(m.get("swap_percent"))
    tl = ctx.get("recent_telemetry") or []
    ram_slope = 0.0
    ram_series = [t.get("metrics", {}).get("ram_percent") for t in tl
                  if isinstance(t, dict) and isinstance(t.get("metrics", {}).get("ram_percent"), (int, float))]
    if len(ram_series) >= 2:
        ram_slope = (ram_series[-1] - ram_series[0]) / max(1, len(ram_series) - 1)
    feats = [ram_pct, leak, ecc_errors, swap_pct, ram_slope]
    had = [r_had, leak_had, ecc_had, sw_had, len(ram_series) >= 2]
    coverage = sum(1 for h in had if h) / len(had)
    raw = {
        "ram_percent": ram_pct if r_had else None,
        "memory_leak_detected": bool(leak) if leak_had else None,
        "ecc_errors": ecc_errors if ecc_had else None,
        "swap_percent": swap_pct if sw_had else None,
        "ram_slope_per_sample": ram_slope,
    }
    return feats, coverage, raw


def features_network(ctx: dict[str, Any]) -> tuple[list[float], float, dict[str, Any]]:
    m = ctx.get("metrics") or {}
    device = ctx.get("device") or {}
    adapters = m.get("adapters") or []
    adapters_up = sum(1 for a in adapters if isinstance(a, dict) and a.get("is_up"))
    adapters_total = len(adapters)
    up_ratio = (adapters_up / adapters_total) if adapters_total > 0 else 1.0
    latency, lat_had = _num(m.get("latency_ms"))
    packet_loss, pl_had = _num(m.get("packet_loss_percent"))
    errors, er_had = _num(m.get("network_errors"))
    minutes_offline = _minutes_since(device.get("last_seen")) if not device.get("is_online") else 0.0
    feats = [1.0 - up_ratio, latency, packet_loss, errors, min(minutes_offline, 60.0)]
    had = [adapters_total > 0, lat_had, pl_had, er_had, bool(device.get("last_seen"))]
    coverage = sum(1 for h in had if h) / len(had)
    raw = {
        "adapters_up": adapters_up,
        "adapters_total": adapters_total,
        "latency_ms": latency if lat_had else None,
        "packet_loss_percent": packet_loss if pl_had else None,
        "network_errors": errors if er_had else None,
        "minutes_since_last_seen": minutes_offline if minutes_offline else None,
    }
    return feats, coverage, raw


FEATURE_BUILDERS = {
    "ssd": features_ssd,
    "fan": features_fan,
    "cpu_thermal": features_cpu_thermal,
    "battery": features_battery,
    "memory": features_memory,
    "network": features_network,
    "crash": None,  # placeholder — set by features_crash() below via post-assign
}


def features_crash(ctx: dict[str, Any]) -> tuple[list[float], float, dict[str, Any]]:
    """Crash-probability features.

    Combines short-term stability signals (BSOD count, unexpected reboots,
    app crashes, event-log errors) with medium-term health slope (declining
    ``score`` in the health timeline is a strong predictor of an impending
    hard crash).
    """
    inv = ctx.get("inventory") or {}
    ch = inv.get("crash_history") or {}
    events = (inv.get("events") or {}).get("events") or []

    bsod   = float(ch.get("bsod_count_7d")     or 0)
    hard   = float(ch.get("hard_reboot_7d")    or 0)
    appcr  = float(ch.get("app_crash_7d")      or 0)
    err_events = float(sum(1 for e in events if isinstance(e, dict) and (e.get("level") == "error")))

    # Health-score slope over the recent timeline is a great early-warning signal.
    timeline = ctx.get("timeline") or []
    slope = _timeline_slope(timeline, key="score")

    m = ctx.get("metrics") or {}
    thermal = 1.0 if m.get("thermal_throttling") else 0.0
    cpu_temp, ct_had = _num(m.get("cpu_temp_c"))
    ram_pct, ram_had = _num(m.get("ram_percent"))

    feats = [bsod, hard, appcr, err_events, -slope,
             thermal, cpu_temp, ram_pct]
    had = [bool(ch), bool(ch), bool(ch),
           bool(events),
           len(timeline) >= 3,
           "thermal_throttling" in m,
           ct_had, ram_had]
    coverage = sum(1 for h in had if h) / len(had)

    raw = {
        "bsod_count_7d":  int(bsod),
        "hard_reboot_7d": int(hard),
        "app_crash_7d":   int(appcr),
        "error_events":   int(err_events),
        "health_slope":   round(slope, 3),
        "thermal_throttling": bool(thermal),
        "cpu_temp_c":     cpu_temp if ct_had else None,
        "ram_percent":    ram_pct  if ram_had else None,
    }
    return feats, coverage, raw


FEATURE_BUILDERS["crash"] = features_crash
