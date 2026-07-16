import React from "react";
import { cn } from "../lib/utils";

export function HealthGauge({ score, size = 120, thickness = 12, showLabel = true }) {
  const s = Math.max(0, Math.min(100, score ?? 0));
  const r = size / 2 - thickness;
  const c = 2 * Math.PI * r;
  const dash = (s / 100) * c;
  // Tier thresholds: Excellent >=90, Good 75-89, Warning 50-74, Critical <50
  const color =
    s >= 90
      ? "text-emerald-400"
      : s >= 75
      ? "text-lime-400"
      : s >= 50
      ? "text-amber-400"
      : "text-red-400";

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={thickness}
          className="stroke-current text-foreground/10"
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={thickness}
          className={cn("stroke-current transition-all duration-700 ease-out", color)}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
          fill="none"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-2xl font-semibold tabular-nums" data-testid="health-gauge-score">
          {score == null ? "—" : Math.round(s)}
        </div>
        {showLabel && (
          <div className="text-[11px] text-muted-foreground mt-0.5">Health</div>
        )}
      </div>
    </div>
  );
}

export const TIER_META = {
  excellent: { label: "Excellent", tone: "healthy", ring: "ring-emerald-500/40" },
  good: { label: "Good", tone: "healthy", ring: "ring-lime-500/40" },
  warning: { label: "Warning", tone: "warning", ring: "ring-amber-500/40" },
  critical: { label: "Critical", tone: "critical", ring: "ring-red-500/40" },
};

export function tierForScore(score) {
  if (score == null) return "critical";
  if (score >= 90) return "excellent";
  if (score >= 75) return "good";
  if (score >= 50) return "warning";
  return "critical";
}

