from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ClientHealthSnapshot:
    score: int
    tier: str            # excellent | good | warning | critical
    reasons: list[str]


def _bucket(score: int) -> str:
    if score >= 90: return "excellent"
    if score >= 75: return "good"
    if score >= 50: return "warning"
    return "critical"


class HealthEngine:
    """Deterministic client-side scorer.

    Deducts points from 100 for the most common local red flags. This engine
    is deliberately conservative and only touches metrics the collectors are
    guaranteed to provide.
    """

    def score(self, metrics: dict[str, Any]) -> ClientHealthSnapshot:
        score = 100
        reasons: list[str] = []

        cpu = _num(metrics.get("cpu_pct") or metrics.get("cpu", {}).get("pct"))
        if cpu is not None and cpu >= 95:
            score -= 12; reasons.append(f"CPU pinned at {cpu:.0f}%")
        elif cpu is not None and cpu >= 85:
            score -= 6;  reasons.append(f"CPU elevated ({cpu:.0f}%)")

        ram = _num(metrics.get("ram_pct") or metrics.get("memory", {}).get("pct"))
        if ram is not None and ram >= 95:
            score -= 10; reasons.append(f"Memory saturated ({ram:.0f}%)")
        elif ram is not None and ram >= 85:
            score -= 4;  reasons.append(f"Memory high ({ram:.0f}%)")

        temp = _num(metrics.get("temp_c") or metrics.get("cpu", {}).get("temperature_c"))
        if temp is not None and temp >= 95:
            score -= 15; reasons.append(f"CPU thermal critical ({temp:.0f}°C)")
        elif temp is not None and temp >= 85:
            score -= 7;  reasons.append(f"CPU thermal high ({temp:.0f}°C)")

        disk = _num(metrics.get("disk_used_pct") or metrics.get("disk", {}).get("used_pct"))
        if disk is not None and disk >= 95:
            score -= 10; reasons.append(f"Disk almost full ({disk:.0f}%)")
        elif disk is not None and disk >= 85:
            score -= 4;  reasons.append(f"Disk usage high ({disk:.0f}%)")

        score = max(0, min(100, score))
        return ClientHealthSnapshot(score=score, tier=_bucket(score), reasons=reasons)


def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
