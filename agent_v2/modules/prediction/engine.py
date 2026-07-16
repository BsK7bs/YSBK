from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import mean
from typing import Any


@dataclass
class PredictionHint:
    kind: str              # cpu_trend | temp_trend | disk_growth | ram_trend
    horizon_minutes: int
    trend: str             # rising | steady | falling
    confidence: float      # 0..1
    detail: str


class PredictionEngine:
    """Sliding-window trend detector using linear regression on recent points."""

    def __init__(self, window: int = 20):
        self.window = window
        self._cpu: deque[float] = deque(maxlen=window)
        self._ram: deque[float] = deque(maxlen=window)
        self._temp: deque[float] = deque(maxlen=window)
        self._disk: deque[float] = deque(maxlen=window)

    def observe(self, metrics: dict[str, Any]) -> None:
        cpu = _num(metrics.get("cpu_pct"))
        ram = _num(metrics.get("ram_pct"))
        temp = _num(metrics.get("temp_c"))
        disk = _num(metrics.get("disk_used_pct"))
        if cpu is not None: self._cpu.append(cpu)
        if ram is not None: self._ram.append(ram)
        if temp is not None: self._temp.append(temp)
        if disk is not None: self._disk.append(disk)

    def hints(self, metrics: dict[str, Any] | None = None) -> list[PredictionHint]:
        if metrics is not None:
            self.observe(metrics)
        out: list[PredictionHint] = []
        for series, kind in ((self._cpu, "cpu_trend"), (self._ram, "ram_trend"),
                              (self._temp, "temp_trend"), (self._disk, "disk_growth")):
            if len(series) < max(5, self.window // 2):
                continue
            slope, conf = _slope(series)
            trend = "rising" if slope > 0.5 else "falling" if slope < -0.5 else "steady"
            if trend == "steady" and conf < 0.6:
                continue
            out.append(PredictionHint(
                kind=kind, horizon_minutes=5, trend=trend,
                confidence=round(conf, 2),
                detail=f"slope={slope:+.2f} pts/sample avg={mean(series):.1f}",
            ))
        return out


def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _slope(series) -> tuple[float, float]:
    n = len(series)
    xs = list(range(n))
    xm, ym = mean(xs), mean(series)
    num = sum((x - xm) * (y - ym) for x, y in zip(xs, series))
    den = sum((x - xm) ** 2 for x in xs) or 1.0
    slope = num / den
    # Confidence proxy: fraction of variance explained (very rough).
    total = sum((y - ym) ** 2 for y in series) or 1.0
    predicted = [ym + slope * (x - xm) for x in xs]
    resid = sum((y - p) ** 2 for y, p in zip(series, predicted))
    r2 = max(0.0, min(1.0, 1 - resid / total))
    return slope, r2
