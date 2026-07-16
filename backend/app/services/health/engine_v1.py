"""V1 rule-based health engine.

Contract: produces a stable ``HealthAssessment`` regardless of which signals
are present. Missing metrics are surfaced (Not Evaluated) rather than
redistributed.

Future engines (V2 ML, V3 AI recommendations) can subclass ``HealthEngine``
and be registered in ``registry.py`` without any API/frontend change.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import HealthEngine
from .contracts import HealthAssessment, HealthTrend, MetricEvaluation, tier_for_score
from .metrics import EVALUATORS, total_weight


class HealthEngineV1RuleBased(HealthEngine):
    version = "v1-rule-based"

    def assess(self, ctx: dict[str, Any]) -> HealthAssessment:
        evaluations: list[MetricEvaluation] = [fn(ctx) for fn in EVALUATORS]
        evaluated = [e for e in evaluations if e.evaluated]
        missing = [e for e in evaluations if not e.evaluated]

        weight_total = total_weight() or 100
        weight_evaluated = sum(e.weight for e in evaluated)
        total_deduction = round(sum(e.deduction for e in evaluated), 2)
        raw_score = 100.0 - total_deduction
        score = int(round(max(0.0, min(100.0, raw_score))))

        completeness = int(round(100.0 * weight_evaluated / weight_total))

        # Failure risk: blend of lost score and count of high/critical metrics.
        high_or_worse = sum(1 for e in evaluated if e.severity in ("high", "critical"))
        base_risk = 100 - score
        risk = int(round(min(100.0, base_risk + high_or_worse * 6)))

        # Confidence: how much of the score is backed by real signal, boosted
        # by timeline density (more samples → higher confidence).
        timeline = ctx.get("timeline") or []
        sample_boost = min(20, int(len(timeline) / 3))  # up to +20 pts
        confidence = int(round(min(100.0, completeness * 0.8 + sample_boost)))

        trend = _compute_trend(timeline, current_score=score)

        return HealthAssessment(
            engine_version=self.version,
            computed_at=datetime.now(timezone.utc),
            score=score,
            tier=tier_for_score(score),
            trend=trend,
            data_completeness_percent=completeness,
            confidence_percent=confidence,
            failure_risk_percent=risk,
            evaluated_metrics=evaluated,
            missing_metrics=missing,
            total_deduction=total_deduction,
            total_weight_evaluated=weight_evaluated,
        )


def _compute_trend(timeline: list[dict[str, Any]], current_score: int) -> HealthTrend:
    """Determine trend from the last few timeline points (linear slope)."""
    if not timeline or len(timeline) < 3:
        return "unknown"
    # Timeline is expected to be time-ordered ascending or descending; sort by ts asc.
    try:
        pts = sorted(
            [t for t in timeline if isinstance(t, dict) and t.get("score") is not None],
            key=lambda t: t.get("ts") or "",
        )
    except Exception:
        pts = timeline
    if len(pts) < 3:
        return "unknown"
    tail = pts[-min(len(pts), 20):]
    n = len(tail)
    xs = list(range(n))
    ys = [float(t.get("score") or 0) for t in tail]
    # Add the current live score as the latest sample too.
    xs.append(n)
    ys.append(float(current_score))
    n2 = len(xs)
    sx = sum(xs)
    sy = sum(ys)
    sxy = sum(a * b for a, b in zip(xs, ys))
    sxx = sum(a * a for a in xs)
    denom = n2 * sxx - sx * sx
    if denom == 0:
        return "stable"
    slope = (n2 * sxy - sx * sy) / denom
    if slope > 0.3:
        return "improving"
    if slope < -0.3:
        return "declining"
    return "stable"
