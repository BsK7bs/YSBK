"""Prediction engine: combines rule-based heuristics with sklearn model output.

Produces a ``PredictionReport`` per device containing one ``Prediction`` for
each supported failure type. Each prediction includes:

    * ``probability_percent``   0-100 combined score
    * ``confidence_percent``    quality/coverage of the input signals
    * ``severity``              risk band (low/medium/high/critical)
    * ``reason``                human-readable explanation
    * ``recommendation``        actionable next step

Design notes
------------
* We favour explainability over raw accuracy. The final ``probability_percent``
  is a weighted blend of a rule score (60%) and the sklearn model score (40%).
  When feature coverage is very low we clamp confidence and downweight the
  final probability so the UI does not over-alert on noisy inputs.
* All models are lazily trained on synthetic data (see ``models.py``); no
  external labelled data is required for cold-start.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np

from .features import FEATURE_BUILDERS
from .models import get_model

ENGINE_VERSION = "prediction-v2-hybrid-horizons"

FAILURE_TYPES = ["ssd", "fan", "cpu_thermal", "battery", "memory", "network", "crash"]

FAILURE_LABELS: dict[str, str] = {
    "ssd": "Disk / SSD Failure",
    "fan": "Fan Failure",
    "cpu_thermal": "Overheating",
    "battery": "Battery Failure",
    "memory": "Memory Failure",
    "network": "Network Failure",
    "crash": "Crash Probability",
}

FAILURE_RECOMMENDATIONS: dict[str, str] = {
    "ssd": "Back up critical data and replace the drive proactively. Schedule a spare.",
    "fan": "Inspect fans for obstruction/wear; verify thermal paste and case airflow.",
    "cpu_thermal": "Reduce sustained load, clean cooling assembly, re-apply thermal paste.",
    "battery": "Order a replacement battery; avoid deep discharges until replaced.",
    "memory": "Run memtest86; identify leaking processes; consider adding RAM.",
    "network": "Verify cabling / Wi-Fi signal; restart adapter; check switch/AP logs.",
    "crash": "Review recent minidumps + Kernel-Power events; roll back the last driver update or Windows quality update if crashes started at that boundary.",
}


@dataclass
class Prediction:
    failure_type: str
    label: str
    probability_percent: float
    confidence_percent: float
    severity: str
    reason: str
    recommendation: str
    features: dict[str, Any] = field(default_factory=dict)
    model_probability_percent: float = 0.0
    rule_probability_percent: float = 0.0
    # Time-to-failure horizons (0-100 each). Semantics: probability that this
    # failure materialises within the given window if no remediation is done.
    probability_7d: float = 0.0
    probability_30d: float = 0.0
    probability_90d: float = 0.0
    # Best-fit "device likely to fail within N days" bucket for the UI.
    likely_within_days: int | None = None


@dataclass
class PredictionReport:
    device_id: str | None
    engine_version: str
    ts: str
    predictions: list[Prediction]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "engine_version": self.engine_version,
            "ts": self.ts,
            "predictions": [
                {
                    "failure_type": p.failure_type,
                    "label": p.label,
                    "probability_percent": round(p.probability_percent, 1),
                    "confidence_percent": round(p.confidence_percent, 1),
                    "severity": p.severity,
                    "reason": p.reason,
                    "recommendation": p.recommendation,
                    "features": p.features,
                    "model_probability_percent": round(p.model_probability_percent, 1),
                    "rule_probability_percent": round(p.rule_probability_percent, 1),
                    "probability_7d":  round(p.probability_7d, 1),
                    "probability_30d": round(p.probability_30d, 1),
                    "probability_90d": round(p.probability_90d, 1),
                    "likely_within_days": p.likely_within_days,
                }
                for p in self.predictions
            ],
        }


# ---------------------------------------------------------------------------
# Rule-based scoring (0-100).
# Returns (rule_probability, top_reasons: list[str]).
# ---------------------------------------------------------------------------

def _rule_ssd(raw: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if raw.get("smart_failing"):
        score += 70
        reasons.append("SMART self-test reports a failing assessment")
    ra = raw.get("reallocated_sectors")
    if isinstance(ra, (int, float)) and ra > 0:
        add = min(20.0, ra / 5.0)
        score += add
        if add >= 5:
            reasons.append(f"{int(ra)} reallocated sectors detected")
    pe = raw.get("pending_sectors")
    if isinstance(pe, (int, float)) and pe > 0:
        add = min(20.0, pe / 3.0)
        score += add
        if add >= 5:
            reasons.append(f"{int(pe)} pending sectors")
    hp = raw.get("disk_health_percent")
    if isinstance(hp, (int, float)) and hp < 70:
        add = (70 - hp) * 0.8
        score += add
        reasons.append(f"Drive health at {hp:.0f}%")
    conf = raw.get("ssd_failure_confidence")
    if isinstance(conf, (int, float)) and conf >= 50:
        score = max(score, conf)
        reasons.append(f"Predictive model confidence {conf:.0f}%")
    return min(100.0, score), reasons


def _rule_fan(raw: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if raw.get("fan_zero_rpm"):
        score += 60
        reasons.append("At least one fan reporting 0 RPM")
    if raw.get("fan_abnormal_status"):
        score += 35
        reasons.append("Fan status reported as abnormal/failed")
    tc = raw.get("cpu_temp_c")
    if isinstance(tc, (int, float)) and tc >= 85:
        score += min(20.0, (tc - 80) * 1.5)
        reasons.append(f"CPU temperature {tc:.0f}°C (elevated)")
    return min(100.0, score), reasons


def _rule_cpu_thermal(raw: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    tc = raw.get("cpu_temp_c")
    if isinstance(tc, (int, float)):
        if tc >= 95:
            score += 70
            reasons.append(f"CPU temperature {tc:.0f}°C (critical band)")
        elif tc >= 85:
            score += 45
            reasons.append(f"CPU temperature {tc:.0f}°C (high)")
        elif tc >= 75:
            score += 20
            reasons.append(f"CPU temperature {tc:.0f}°C (warm)")
    if raw.get("thermal_throttling"):
        score += 25
        reasons.append("Thermal throttling reported by CPU")
    slope = raw.get("cpu_temp_slope_per_sample") or 0
    if isinstance(slope, (int, float)) and slope > 1.5:
        score += min(15.0, slope * 3)
        reasons.append("CPU temperature trending up quickly")
    return min(100.0, score), reasons


def _rule_battery(raw: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    hp = raw.get("battery_health_percent")
    if isinstance(hp, (int, float)):
        if hp < 40:
            score += 70
            reasons.append(f"Battery health {hp:.0f}% (severely degraded)")
        elif hp < 60:
            score += 45
            reasons.append(f"Battery health {hp:.0f}% (degraded)")
        elif hp < 80:
            score += 20
            reasons.append(f"Battery health {hp:.0f}% (aging)")
    cy = raw.get("cycle_count")
    if isinstance(cy, (int, float)) and cy > 800:
        score += min(20.0, (cy - 800) / 30.0)
        reasons.append(f"High cycle count ({int(cy)})")
    cr = raw.get("capacity_ratio_percent")
    if isinstance(cr, (int, float)) and cr < 60:
        score += (60 - cr) * 0.8
        reasons.append(f"Full-charge capacity at {cr:.0f}% of design")
    return min(100.0, score), reasons


def _rule_memory(raw: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    ram = raw.get("ram_percent")
    if isinstance(ram, (int, float)) and ram >= 85:
        score += min(35.0, (ram - 80) * 3)
        reasons.append(f"RAM usage {ram:.0f}%")
    if raw.get("memory_leak_detected"):
        score += 50
        reasons.append("Memory leak signature detected")
    ecc = raw.get("ecc_errors")
    if isinstance(ecc, (int, float)) and ecc > 0:
        score += min(30.0, ecc)
        reasons.append(f"{int(ecc)} ECC error(s) reported")
    swap = raw.get("swap_percent")
    if isinstance(swap, (int, float)) and swap > 30:
        score += min(15.0, (swap - 30) / 3)
        reasons.append(f"Heavy swap usage {swap:.0f}%")
    slope = raw.get("ram_slope_per_sample") or 0
    if isinstance(slope, (int, float)) and slope > 1:
        score += min(15.0, slope * 4)
        reasons.append("RAM usage climbing steadily")
    return min(100.0, score), reasons


def _rule_network(raw: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    total = raw.get("adapters_total") or 0
    up = raw.get("adapters_up") or 0
    if total > 0 and up == 0:
        score += 60
        reasons.append("No active network adapters")
    lat = raw.get("latency_ms")
    if isinstance(lat, (int, float)) and lat > 300:
        score += min(25.0, (lat - 300) / 30)
        reasons.append(f"High latency {lat:.0f} ms")
    pl = raw.get("packet_loss_percent")
    if isinstance(pl, (int, float)) and pl > 2:
        score += min(30.0, pl * 3)
        reasons.append(f"Packet loss {pl:.1f}%")
    err = raw.get("network_errors")
    if isinstance(err, (int, float)) and err > 10:
        score += min(20.0, err / 5)
        reasons.append(f"{int(err)} recent adapter errors")
    off = raw.get("minutes_since_last_seen")
    if isinstance(off, (int, float)) and off > 5:
        score += min(30.0, off / 2)
        reasons.append(f"Device unreachable for ~{off:.0f} min")
    return min(100.0, score), reasons


def _rule_crash(raw: dict[str, Any]) -> tuple[float, list[str]]:
    """Crash-probability rule scorer.

    BSODs are the strongest signal (each contributes 25pts up to a 70-pt cap);
    unexpected reboots add up to 30pts; app crashes above baseline 2/wk add up
    to 15pts; a *declining* health-score slope adds up to 20pts.
    """
    score = 0.0
    reasons: list[str] = []
    bsod = raw.get("bsod_count_7d") or 0
    hard = raw.get("hard_reboot_7d") or 0
    appcr = raw.get("app_crash_7d") or 0
    slope = raw.get("health_slope") or 0
    if bsod > 0:
        score += min(70.0, bsod * 25.0)
        reasons.append(f"{int(bsod)} BSOD(s) in the last 7 days")
    if hard > 0:
        score += min(30.0, hard * 6.0)
        reasons.append(f"{int(hard)} unexpected reboot(s) in 7d")
    if appcr > 2:
        score += min(15.0, (appcr - 2) * 1.0)
        reasons.append(f"{int(appcr)} app crashes in 7d")
    if isinstance(slope, (int, float)) and slope < -0.5:
        score += min(20.0, abs(slope) * 10)
        reasons.append("Health score trending downward")
    if raw.get("thermal_throttling"):
        score += 10
        reasons.append("Thermal throttling in play (raises crash risk)")
    return min(100.0, score), reasons


RULE_SCORERS: dict[str, Callable[[dict], tuple[float, list[str]]]] = {
    "ssd": _rule_ssd,
    "fan": _rule_fan,
    "cpu_thermal": _rule_cpu_thermal,
    "battery": _rule_battery,
    "memory": _rule_memory,
    "network": _rule_network,
    "crash": _rule_crash,
}


def _severity_from_probability(p: float) -> str:
    if p >= 80:
        return "critical"
    if p >= 60:
        return "high"
    if p >= 35:
        return "medium"
    if p >= 15:
        return "low"
    return "info"


def _predict_one(failure_type: str, ctx: dict[str, Any]) -> Prediction:
    feats_vec, coverage, raw = FEATURE_BUILDERS[failure_type](ctx)
    rule_score, rule_reasons = RULE_SCORERS[failure_type](raw)

    model = get_model(failure_type)
    proba = model.predict_proba(np.array([feats_vec]))[0]
    # Class 1 is "will fail"; fall back to 0 if the model somehow only saw one class.
    if len(proba) == 2:
        model_score = float(proba[1]) * 100.0
    else:
        model_score = 0.0

    # Blend rule + ML. Rule wins when it is very confident (>=70).
    if rule_score >= 70:
        blended = 0.75 * rule_score + 0.25 * model_score
    else:
        blended = 0.60 * rule_score + 0.40 * model_score

    # Down-weight when we barely have any signal at all.
    if coverage < 0.25:
        blended *= max(0.35, coverage / 0.25)

    confidence = round(min(100.0, 45 + coverage * 55), 1)
    probability = round(min(100.0, max(0.0, blended)), 1)

    if not rule_reasons:
        if probability >= 35:
            rule_reasons = ["Model detected an unusual signature in recent telemetry"]
        else:
            rule_reasons = ["All monitored signals are within nominal ranges"]

    reason = "; ".join(rule_reasons[:3])
    recommendation = FAILURE_RECOMMENDATIONS[failure_type]

    # ----- Time-to-failure horizons ---------------------------------------
    # We treat `probability_percent` as the 90-day probability (the model was
    # trained on "will fail in the medium term" positives), and derive shorter
    # windows by exponential decay.  Under stress signals (thermal, BSOD,
    # SMART flagged) the near-term windows accelerate.
    p90 = probability
    # Base decay: 30d ~= 65% of 90d, 7d ~= 30% of 90d.
    p30 = p90 * 0.65
    p7 = p90 * 0.30
    # Accelerators — near-term risk climbs sharply for smoking-gun signals.
    accel = 0.0
    if raw.get("smart_failing"):        accel += 0.35
    if raw.get("fan_zero_rpm"):         accel += 0.30
    if raw.get("thermal_throttling"):   accel += 0.15
    if raw.get("bsod_count_7d") and raw["bsod_count_7d"] > 0: accel += 0.35
    if isinstance(raw.get("cpu_temp_c"), (int, float)) and raw["cpu_temp_c"] >= 95: accel += 0.20
    if accel:
        p7  = min(100.0, p7  + p90 * accel)
        p30 = min(100.0, p30 + p90 * accel * 0.6)

    p7  = round(min(100.0, p7),  1)
    p30 = round(min(100.0, p30), 1)
    p90 = round(min(100.0, p90), 1)

    likely: int | None
    if   p7  >= 40: likely = 7
    elif p30 >= 40: likely = 30
    elif p90 >= 40: likely = 90
    else:           likely = None

    return Prediction(
        failure_type=failure_type,
        label=FAILURE_LABELS[failure_type],
        probability_percent=probability,
        confidence_percent=confidence,
        severity=_severity_from_probability(probability),
        reason=reason,
        recommendation=recommendation,
        features=raw,
        model_probability_percent=round(model_score, 1),
        rule_probability_percent=round(rule_score, 1),
        probability_7d=p7,
        probability_30d=p30,
        probability_90d=p90,
        likely_within_days=likely,
    )


def predict_device(ctx: dict[str, Any]) -> PredictionReport:
    """Compute predictions for every supported failure type."""
    device_id = (ctx.get("device") or {}).get("id")
    ts = datetime.now(timezone.utc).isoformat()
    preds = [_predict_one(ft, ctx) for ft in FAILURE_TYPES]
    return PredictionReport(
        device_id=device_id,
        engine_version=ENGINE_VERSION,
        ts=ts,
        predictions=preds,
    )
