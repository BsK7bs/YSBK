import React from "react";
import { cn } from "../lib/utils";
import { riskLabel } from "../lib/format";

const STYLES = {
  healthy: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  warning: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  "high-risk": "bg-orange-500/10 text-orange-300 border-orange-500/30",
  critical: "bg-red-500/10 text-red-300 border-red-500/30",
  offline: "bg-slate-500/10 text-slate-300 border-slate-500/30",
  info: "bg-cyan-500/10 text-cyan-300 border-cyan-500/30",
  online: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
};

const DOTS = {
  healthy: "bg-emerald-500",
  warning: "bg-amber-500",
  "high-risk": "bg-orange-500",
  critical: "bg-red-500",
  offline: "bg-slate-400",
  info: "bg-cyan-500",
  online: "bg-emerald-500",
};

export function StatBadge({ variant = "info", pulse = false, children, className, testId, ...rest }) {
  const finalTestId = testId ?? rest["data-testid"];
  const passthroughDom = { ...rest };
  delete passthroughDom["data-testid"];
  return (
    <span
      data-testid={finalTestId}
      className={cn(
        "inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-xs font-medium border",
        STYLES[variant] || STYLES.info,
        className,
      )}
      {...passthroughDom}
    >
      <span className={cn("h-2 w-2 rounded-full", DOTS[variant] || DOTS.info, pulse && "animate-pulse-dot")} />
      <span>{children}</span>
    </span>
  );
}

export function RiskBadge({ risk }) {
  const map = {
    healthy: "healthy",
    warning: "warning",
    high_risk: "high-risk",
    critical: "critical",
    offline: "offline",
  };
  const variant = map[risk] || "offline";
  return <StatBadge variant={variant}>{riskLabel(risk)}</StatBadge>;
}

export function OnlineBadge({ online }) {
  return (
    <StatBadge variant={online ? "online" : "offline"} pulse={online}>
      {online ? "Online" : "Offline"}
    </StatBadge>
  );
}
