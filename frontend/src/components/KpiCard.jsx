import React from "react";
import { motion } from "framer-motion";
import { cn } from "../lib/utils";
import { formatNumber } from "../lib/format";

export function KpiCard({ label, value, hint, icon: Icon, tone = "default", suffix, className, testId }) {
  const toneRing = {
    default: "bg-primary/10 text-primary border-primary/25",
    success: "bg-emerald-500/10 text-emerald-300 border-emerald-500/25",
    warning: "bg-amber-500/10 text-amber-300 border-amber-500/25",
    critical: "bg-red-500/10 text-red-300 border-red-500/25",
    info: "bg-cyan-500/10 text-cyan-300 border-cyan-500/25",
  }[tone] || "bg-primary/10 text-primary border-primary/25";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.26, ease: [0.2, 0.8, 0.2, 1] }}
      className={cn(
        "rounded-2xl border border-border bg-card p-4 sm:p-5 shadow-[var(--shadow-1)]",
        "relative overflow-hidden",
        className,
      )}
      data-testid={testId}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
            {label}
          </div>
          <div className="mt-2 text-3xl font-semibold tracking-tight tabular-nums" data-testid={`${testId}-value`}>
            {typeof value === "number" ? formatNumber(value) : value ?? "—"}
            {suffix && <span className="ml-1 text-lg text-muted-foreground">{suffix}</span>}
          </div>
        </div>
        {Icon && (
          <div className={cn("h-10 w-10 rounded-xl border flex items-center justify-center", toneRing)}>
            <Icon className="h-4 w-4" />
          </div>
        )}
      </div>
      {hint && <div className="mt-3 text-xs text-muted-foreground">{hint}</div>}
    </motion.div>
  );
}
