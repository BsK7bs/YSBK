import React, { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useNavigate } from "react-router-dom";
import {
  Brain, HardDrive, Fan, Thermometer, BatteryCharging, MemoryStick, Wifi,
  ArrowRight, RefreshCw, Loader2, TrendingUp, ChevronRight,
} from "lucide-react";
import { api } from "../lib/api";
import { StatBadge } from "./StatBadge";

const ICON_BY_TYPE = {
  ssd: HardDrive,
  fan: Fan,
  cpu_thermal: Thermometer,
  battery: BatteryCharging,
  memory: MemoryStick,
  network: Wifi,
};

const SEVERITY_TO_VARIANT = {
  critical: "critical",
  high: "warning",
  medium: "warning",
  low: "info",
  info: "healthy",
};

function probabilityColor(p) {
  if (p >= 80) return "#ef4444";
  if (p >= 60) return "#f97316";
  if (p >= 35) return "#f59e0b";
  if (p >= 15) return "#3b82f6";
  return "#22c55e";
}

function Row({ item, onOpen }) {
  const Icon = ICON_BY_TYPE[item.worst.failure_type] || Brain;
  const color = probabilityColor(item.worst.probability_percent);
  return (
    <motion.button
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      onClick={() => onOpen(item.id)}
      data-testid="top-risk-row"
      className="w-full text-left rounded-xl border border-border/70 bg-foreground/[0.02] hover:bg-foreground/[0.05] hover:border-primary/60 transition-colors p-3 group"
    >
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-foreground/[0.05] p-2 shrink-0"><Icon className="h-4 w-4 text-primary" /></div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <div className="text-sm font-semibold truncate" data-testid="top-risk-device-name">
              {item.display_name || item.hostname || item.id.slice(0, 8)}
            </div>
            <StatBadge variant={SEVERITY_TO_VARIANT[item.worst.severity] || "info"} className="ml-auto">
              {item.worst.severity}
            </StatBadge>
          </div>
          <div className="mt-1 flex items-center gap-3">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{item.worst.label}</div>
            <div className="ml-auto flex items-baseline gap-1">
              <div className="text-lg font-semibold tabular-nums leading-none" style={{ color }} data-testid="top-risk-probability">
                {item.worst.probability_percent.toFixed(1)}%
              </div>
              <div className="text-[10px] text-muted-foreground">· {item.worst.confidence_percent.toFixed(0)}% conf</div>
            </div>
          </div>
          <div className="mt-1 text-[11px] text-muted-foreground line-clamp-1">{item.worst.reason}</div>
        </div>
        <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors shrink-0" />
      </div>
    </motion.button>
  );
}

export function TopAtRiskWidget() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [minProb, setMinProb] = useState(0);

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true); else setLoading(true);
    setError(null);
    try {
      const { data } = await api.get("/predictions/fleet/top-risk", {
        params: { limit: 8, min_probability: minProb },
      });
      setItems(data.items || []);
      setTotal(data.total_devices || 0);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "Failed to load");
    } finally {
      setLoading(false); setRefreshing(false);
    }
  }, [minProb]);

  useEffect(() => { load(); }, [load]);
  // Silent refresh every 60s.
  useEffect(() => {
    const t = setInterval(() => load(true), 60_000);
    return () => clearInterval(t);
  }, [load]);

  const open = (id) => navigate(`/app/devices/${id}?tab=ai-prediction`);

  const criticalCount = useMemo(
    () => items.filter((i) => i.worst.severity === "critical").length,
    [items],
  );

  return (
    <motion.div
      layout
      className="lg:col-span-12 rounded-2xl border border-border bg-card p-4 sm:p-5 shadow-[var(--shadow-1)]"
      data-testid="top-at-risk-widget"
    >
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <div className="rounded-xl bg-primary/10 p-2"><Brain className="h-4 w-4 text-primary" /></div>
          <div>
            <div className="text-sm font-semibold flex items-center gap-2">
              Top at-risk devices
              {criticalCount > 0 && (
                <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider text-red-300 bg-red-500/10 border border-red-500/30 rounded-full px-2 py-0.5" data-testid="top-risk-critical-badge">
                  <TrendingUp className="h-3 w-3" /> {criticalCount} critical
                </span>
              )}
            </div>
            <div className="text-[11px] text-muted-foreground">
              AI Prediction · rule engine + Scikit-learn · {total} device{total === 1 ? "" : "s"} scanned
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 mr-2">
            {[
              { label: "All", v: 0 },
              { label: "≥35%", v: 35 },
              { label: "≥60%", v: 60 },
            ].map((opt) => (
              <button
                key={opt.v}
                onClick={() => setMinProb(opt.v)}
                className={`text-[11px] px-2 py-1 rounded-full border ${minProb === opt.v ? "border-primary text-primary bg-primary/10" : "border-border text-muted-foreground hover:text-foreground"}`}
                data-testid={`top-risk-filter-${opt.v}`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button
            onClick={() => load(true)}
            disabled={refreshing}
            className="text-xs px-2 py-1 rounded-full border border-border text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
            data-testid="top-risk-refresh"
          >
            {refreshing ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
            Recompute
          </button>
          <button
            onClick={() => navigate("/app/devices?sort=risk")}
            className="text-xs text-primary hover:underline inline-flex items-center gap-1"
            data-testid="top-risk-view-all"
          >
            View all <ArrowRight className="h-3 w-3" />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-24 text-xs text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin mr-2" /> Predicting…
        </div>
      ) : error ? (
        <div className="rounded-xl border border-dashed border-red-500/40 p-4 text-sm text-red-300">{error}</div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-6 text-sm text-muted-foreground text-center">
          {minProb > 0
            ? `No devices above ${minProb}% predicted risk. Fleet looks clean at this threshold. 🎉`
            : "No devices to evaluate yet. Enroll a device to start receiving AI predictions."}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
          <AnimatePresence initial={false}>
            {items.map((it) => (
              <Row key={it.id} item={it} onOpen={open} />
            ))}
          </AnimatePresence>
        </div>
      )}
    </motion.div>
  );
}

export default TopAtRiskWidget;
