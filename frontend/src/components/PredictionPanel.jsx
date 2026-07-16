import React, { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Brain, HardDrive, Fan, Thermometer, BatteryCharging, MemoryStick, Wifi,
  Loader2, RefreshCw, TrendingUp, ChevronDown, ChevronRight, Sparkles,
} from "lucide-react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
} from "recharts";
import { api } from "../lib/api";
import { StatBadge } from "./StatBadge";
import { EmptyState } from "./EmptyState";
import { Button } from "./ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./ui/tabs";

const FAILURE_META = {
  ssd:         { label: "SSD Failure",       icon: HardDrive,       tone: "critical" },
  fan:         { label: "Fan Failure",       icon: Fan,             tone: "warning" },
  cpu_thermal: { label: "CPU Overheating",   icon: Thermometer,     tone: "warning" },
  battery:    { label: "Battery Failure",   icon: BatteryCharging, tone: "warning" },
  memory:      { label: "Memory Failure",    icon: MemoryStick,     tone: "warning" },
  network:     { label: "Network Failure",   icon: Wifi,            tone: "info" },
};

const RANGES = [
  { key: "1h",  label: "1h"  },
  { key: "24h", label: "24h" },
  { key: "7d",  label: "7d"  },
  { key: "30d", label: "30d" },
];

const SEVERITY_TO_VARIANT = {
  critical: "critical",
  high: "warning",
  medium: "warning",
  low: "info",
  info: "healthy",
};

function severityText(s) {
  return (s || "info").replace(/^./, (c) => c.toUpperCase());
}

function probabilityColor(p) {
  if (p >= 80) return "#ef4444"; // red
  if (p >= 60) return "#f97316"; // orange
  if (p >= 35) return "#f59e0b"; // amber
  if (p >= 15) return "#3b82f6"; // blue
  return "#22c55e";              // green
}

function niceTime(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function PredictionCard({ p, timeline, onSelect, active }) {
  const meta = FAILURE_META[p.failure_type] || { label: p.failure_type, icon: Brain, tone: "info" };
  const Icon = meta.icon;
  const color = probabilityColor(p.probability_percent);
  const series = (timeline || []).map((t) => ({
    ts: t.ts,
    probability: t.probability_percent,
    confidence: t.confidence_percent,
  }));
  return (
    <motion.button
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      onClick={onSelect}
      data-testid={`prediction-card-${p.failure_type}`}
      className={`text-left rounded-2xl border ${active ? "border-primary/70 shadow-[0_0_0_1px_hsl(var(--primary))]" : "border-border"} bg-card p-5 hover:border-primary/50 transition-colors`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="rounded-xl bg-foreground/[0.05] p-2"><Icon className="h-4 w-4 text-primary" /></div>
          <div>
            <div className="text-sm font-semibold">{meta.label}</div>
            <div className="text-[11px] text-muted-foreground uppercase tracking-wider">{p.failure_type}</div>
          </div>
        </div>
        <StatBadge variant={SEVERITY_TO_VARIANT[p.severity] || "info"} testId={`prediction-severity-${p.failure_type}`}>{severityText(p.severity)}</StatBadge>
      </div>

      <div className="mt-4 flex items-end gap-6">
        <div>
          <div className="text-[11px] uppercase text-muted-foreground tracking-wider">Failure probability</div>
          <div className="text-3xl font-semibold tabular-nums" style={{ color }} data-testid={`prediction-probability-${p.failure_type}`}>{p.probability_percent.toFixed(1)}%</div>
        </div>
        <div>
          <div className="text-[11px] uppercase text-muted-foreground tracking-wider">Confidence</div>
          <div className="text-lg font-medium tabular-nums" data-testid={`prediction-confidence-${p.failure_type}`}>{p.confidence_percent.toFixed(0)}%</div>
        </div>
      </div>

      {series.length >= 2 && (
        <div className="mt-3 h-14 w-full min-w-[80px]">
          <ResponsiveContainer width="99%" height="100%">
            <LineChart data={series} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
              <Line type="monotone" dataKey="probability" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
              <YAxis hide domain={[0, 100]} />
              <XAxis hide dataKey="ts" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="mt-3 text-xs text-muted-foreground line-clamp-2">{p.reason}</div>
    </motion.button>
  );
}

function DetailPanel({ p, timeline, range, onRangeChange }) {
  if (!p) return null;
  const meta = FAILURE_META[p.failure_type] || { label: p.failure_type, icon: Brain };
  const Icon = meta.icon;
  const color = probabilityColor(p.probability_percent);
  const series = (timeline || []).map((t) => ({
    ts: t.ts,
    probability: t.probability_percent,
    confidence: t.confidence_percent,
  }));
  const featureEntries = Object.entries(p.features || {}).filter(([, v]) => v !== null && v !== undefined && v !== "");
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl border border-border bg-card p-5"
      data-testid="prediction-detail-panel"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="rounded-xl bg-foreground/[0.05] p-2"><Icon className="h-5 w-5 text-primary" /></div>
          <div>
            <div className="text-base font-semibold">{meta.label}</div>
            <div className="text-xs text-muted-foreground">Latest evaluation · {niceTime(p.ts_local || null)}</div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {RANGES.map((r) => (
            <button
              key={r.key}
              onClick={() => onRangeChange(r.key)}
              className={`text-xs px-2.5 py-1 rounded-full border ${range === r.key ? "border-primary text-primary bg-primary/10" : "border-border text-muted-foreground hover:text-foreground"}`}
              data-testid={`prediction-range-${r.key}`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-5">
        <div className="rounded-xl border border-border/70 p-4 bg-foreground/[0.02]">
          <div className="text-[11px] uppercase text-muted-foreground tracking-wider">Probability</div>
          <div className="text-2xl font-semibold tabular-nums" style={{ color }}>{p.probability_percent.toFixed(1)}%</div>
          <div className="text-[11px] mt-1 text-muted-foreground">rule {p.rule_probability_percent.toFixed(0)}% · model {p.model_probability_percent.toFixed(0)}%</div>
        </div>
        <div className="rounded-xl border border-border/70 p-4 bg-foreground/[0.02]">
          <div className="text-[11px] uppercase text-muted-foreground tracking-wider">Confidence</div>
          <div className="text-2xl font-semibold tabular-nums">{p.confidence_percent.toFixed(0)}%</div>
          <div className="text-[11px] mt-1 text-muted-foreground">based on telemetry coverage</div>
        </div>
        <div className="rounded-xl border border-border/70 p-4 bg-foreground/[0.02]">
          <div className="text-[11px] uppercase text-muted-foreground tracking-wider">Severity</div>
          <div className="mt-1"><StatBadge variant={SEVERITY_TO_VARIANT[p.severity] || "info"}>{severityText(p.severity)}</StatBadge></div>
        </div>
      </div>

      <div className="mt-6">
        <div className="text-xs font-semibold uppercase text-muted-foreground tracking-wider mb-2">Prediction timeline</div>
        {series.length < 2 ? (
          <div className="h-40 flex items-center justify-center text-xs text-muted-foreground border border-dashed border-border rounded-xl">Not enough history yet — open this device over time to build the timeline.</div>
        ) : (
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="ts" tick={{ fontSize: 10 }} tickFormatter={(v) => { try { return new Date(v).toLocaleTimeString(); } catch { return v; } }} />
                <YAxis domain={[0, 100]} width={36} tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", fontSize: 12 }} />
                <ReferenceLine y={80} stroke="#ef4444" strokeDasharray="4 4" />
                <ReferenceLine y={60} stroke="#f97316" strokeDasharray="4 4" />
                <Line type="monotone" dataKey="probability" name="Failure %" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="confidence" name="Confidence %" stroke="hsl(var(--muted-foreground))" strokeWidth={1.5} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-xl border border-border/70 p-4 bg-foreground/[0.02]">
          <div className="text-xs font-semibold uppercase text-muted-foreground tracking-wider mb-2">Reason</div>
          <div className="text-sm">{p.reason || "—"}</div>
        </div>
        <div className="rounded-xl border border-border/70 p-4 bg-foreground/[0.02]">
          <div className="text-xs font-semibold uppercase text-muted-foreground tracking-wider mb-2 flex items-center gap-2"><Sparkles className="h-3.5 w-3.5 text-primary" /> Recommendation</div>
          <div className="text-sm">{p.recommendation || "—"}</div>
        </div>
      </div>

      {featureEntries.length > 0 && (
        <details className="mt-4 group">
          <summary className="text-xs font-semibold uppercase text-muted-foreground tracking-wider cursor-pointer list-none flex items-center gap-1">
            <ChevronRight className="h-3.5 w-3.5 group-open:hidden" />
            <ChevronDown className="h-3.5 w-3.5 hidden group-open:inline" />
            Signals used
          </summary>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
            {featureEntries.map(([k, v]) => (
              <div key={k} className="flex items-center justify-between text-xs px-3 py-2 rounded-lg bg-foreground/[0.03] border border-border/60">
                <span className="text-muted-foreground font-mono">{k}</span>
                <span className="tabular-nums font-medium">{typeof v === "number" ? v.toFixed(2) : String(v)}</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </motion.div>
  );
}

function HistoryList({ items }) {
  if (!items || items.length === 0) {
    return <div className="text-xs text-muted-foreground">No historical evaluations yet.</div>;
  }
  return (
    <div className="rounded-2xl border border-border bg-card overflow-hidden" data-testid="prediction-history-list">
      <table className="min-w-full text-sm">
        <thead className="bg-foreground/[0.04] text-[11px] uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="px-4 py-2 text-left">When</th>
            <th className="px-4 py-2 text-left">Highest risk</th>
            <th className="px-4 py-2 text-right">Probability</th>
            <th className="px-4 py-2 text-right">Confidence</th>
            <th className="px-4 py-2 text-left">Severity</th>
          </tr>
        </thead>
        <tbody>
          {items.slice().reverse().map((entry, idx) => {
            const preds = entry.predictions || [];
            const top = preds.reduce((a, b) => (b.probability_percent > (a?.probability_percent ?? -1) ? b : a), null);
            if (!top) return null;
            const meta = FAILURE_META[top.failure_type] || { label: top.failure_type };
            return (
              <tr key={`${entry.ts}-${idx}`} className="border-t border-border">
                <td className="px-4 py-2 text-xs text-muted-foreground">{niceTime(entry.ts)}</td>
                <td className="px-4 py-2">{meta.label}</td>
                <td className="px-4 py-2 text-right tabular-nums" style={{ color: probabilityColor(top.probability_percent) }}>{top.probability_percent.toFixed(1)}%</td>
                <td className="px-4 py-2 text-right tabular-nums">{top.confidence_percent.toFixed(0)}%</td>
                <td className="px-4 py-2"><StatBadge variant={SEVERITY_TO_VARIANT[top.severity] || "info"}>{severityText(top.severity)}</StatBadge></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function PredictionPanel({ deviceId }) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [report, setReport] = useState(null);
  const [selected, setSelected] = useState(null);
  const [range, setRange] = useState("24h");
  const [timeline, setTimeline] = useState({ items: [], full: [] });
  const [error, setError] = useState(null);

  const load = useCallback(async (opts = {}) => {
    if (!deviceId) return;
    if (opts.silent) setRefreshing(true); else setLoading(true);
    setError(null);
    try {
      const [{ data: current }, { data: hist }] = await Promise.all([
        api.get(`/devices/${deviceId}/predictions`),
        api.get(`/devices/${deviceId}/predictions/timeline`, { params: { range } }),
      ]);
      setReport(current);
      setTimeline({ items: hist.items || [], full: hist.items || [] });
      if (!selected && current?.predictions?.length) {
        setSelected(current.predictions[0].failure_type);
      }
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "Failed to load predictions");
    } finally {
      setLoading(false); setRefreshing(false);
    }
  }, [deviceId, range, selected]);

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [deviceId]);
  useEffect(() => { if (deviceId) load({ silent: true }); /* eslint-disable-next-line */ }, [range]);

  const selectedPrediction = useMemo(() => {
    return (report?.predictions || []).find((p) => p.failure_type === selected) || null;
  }, [report, selected]);

  const selectedTimeline = useMemo(() => {
    if (!selected) return [];
    return (timeline.items || []).map((entry) => {
      const p = (entry.predictions || []).find((x) => x.failure_type === selected);
      if (!p) return null;
      return { ts: entry.ts, ...p };
    }).filter(Boolean);
  }, [timeline, selected]);

  const summaryPerCard = useMemo(() => {
    const map = {};
    (timeline.items || []).forEach((entry) => {
      (entry.predictions || []).forEach((p) => {
        (map[p.failure_type] = map[p.failure_type] || []).push({ ts: entry.ts, ...p });
      });
    });
    return map;
  }, [timeline]);

  if (loading && !report) {
    return (
      <div className="flex items-center justify-center h-40 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin mr-2" /> Computing predictions…
      </div>
    );
  }

  if (error) {
    return <EmptyState icon={Brain} title="Prediction unavailable" description={error} />;
  }

  if (!report) {
    return <EmptyState icon={Brain} title="No predictions" description="Enroll a device and start streaming telemetry to power predictions." />;
  }

  const preds = report.predictions || [];
  const worst = preds.reduce((a, b) => (b.probability_percent > (a?.probability_percent ?? -1) ? b : a), null);

  return (
    <div className="space-y-5" data-testid="ai-prediction-panel">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary" />
            <h3 className="text-base font-semibold">AI Prediction · Rule engine + Scikit-learn</h3>
          </div>
          <p className="text-xs text-muted-foreground mt-1">Engine {report.engine_version} · updated {niceTime(report.ts)}</p>
        </div>
        <div className="flex items-center gap-2">
          {worst && worst.probability_percent >= 15 && (
            <div className="text-xs text-muted-foreground flex items-center gap-2 mr-2">
              <TrendingUp className="h-3.5 w-3.5" /> Highest risk: <span className="font-medium text-foreground">{FAILURE_META[worst.failure_type]?.label || worst.failure_type}</span> · <span className="tabular-nums" style={{ color: probabilityColor(worst.probability_percent) }}>{worst.probability_percent.toFixed(1)}%</span>
            </div>
          )}
          <Button variant="outline" size="sm" onClick={() => load({ silent: true })} disabled={refreshing} data-testid="prediction-refresh">
            {refreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />} Recompute
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {preds.map((p) => (
          <PredictionCard
            key={p.failure_type}
            p={p}
            timeline={summaryPerCard[p.failure_type] || []}
            active={selected === p.failure_type}
            onSelect={() => setSelected(p.failure_type)}
          />
        ))}
      </div>

      {selectedPrediction && (
        <DetailPanel
          p={{ ...selectedPrediction, ts_local: report.ts }}
          timeline={selectedTimeline}
          range={range}
          onRangeChange={setRange}
        />
      )}

      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="text-sm font-semibold">Historical predictions</div>
          <div className="text-xs text-muted-foreground">{timeline.items?.length || 0} evaluations in the last {range}</div>
        </div>
        <HistoryList items={timeline.items} />
      </div>
    </div>
  );
}

export default PredictionPanel;
