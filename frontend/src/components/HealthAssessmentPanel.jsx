import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Info,
  Loader2, Minus, TrendingDown, TrendingUp, ShieldAlert, ShieldCheck,
  Cpu, Thermometer, MemoryStick, HardDrive, Database, Wifi, Wand2,
  RefreshCw, PowerOff, Bug, Fan, BatteryMedium, Server, Lock, RotateCw,
} from "lucide-react";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine } from "recharts";
import { api } from "../lib/api";
import { HealthGauge, TIER_META } from "./HealthGauge";
import { StatBadge } from "./StatBadge";
import { LiveIndicator } from "./LiveIndicator";
import { EmptyState } from "./EmptyState";

const METRIC_ICONS = {
  cpu_usage: Cpu,
  cpu_temperature: Thermometer,
  ram_usage: MemoryStick,
  disk_usage: HardDrive,
  ssd_health: Database,
  network_health: Wifi,
  offline_frequency: PowerOff,
  crash_frequency: Bug,
  security_status: Lock,
  windows_updates: RotateCw,
  fan_health: Fan,
  battery_health: BatteryMedium,
  services_health: Server,
};

const SEVERITY_STYLES = {
  ok:       { badge: "healthy", label: "Normal",   text: "text-emerald-300" },
  low:      { badge: "info",    label: "Low",      text: "text-cyan-300" },
  medium:   { badge: "warning", label: "Medium",   text: "text-amber-300" },
  high:     { badge: "high-risk", label: "High",   text: "text-orange-300" },
  critical: { badge: "critical", label: "Critical", text: "text-red-300" },
  unknown:  { badge: "offline", label: "Unknown",  text: "text-slate-300" },
};

const TREND_META = {
  improving: { label: "Improving", icon: TrendingUp,   className: "text-emerald-400" },
  stable:    { label: "Stable",    icon: Minus,        className: "text-slate-300" },
  declining: { label: "Declining", icon: TrendingDown, className: "text-red-400" },
  unknown:   { label: "Collecting", icon: Activity,   className: "text-muted-foreground" },
};

const RANGES = [
  { key: "1h",  label: "Last hour"  },
  { key: "24h", label: "Last 24 h"  },
  { key: "7d",  label: "Last 7 d"   },
  { key: "30d", label: "Last 30 d"  },
];

function Kpi({ label, value, hint, tone = "default", testId }) {
  const toneStyle = {
    default:  "border-border bg-card",
    good:     "border-emerald-500/25 bg-emerald-500/[0.06]",
    warn:     "border-amber-500/25 bg-amber-500/[0.06]",
    critical: "border-red-500/25 bg-red-500/[0.06]",
    info:     "border-cyan-500/25 bg-cyan-500/[0.06]",
  }[tone] || "border-border bg-card";
  return (
    <div className={`rounded-2xl border p-4 ${toneStyle}`} data-testid={testId}>
      <div className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums" data-testid={testId ? `${testId}-value` : undefined}>
        {value}
      </div>
      {hint && <div className="text-[11px] text-muted-foreground mt-1">{hint}</div>}
    </div>
  );
}

function DeductionRow({ ev, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const Icon = METRIC_ICONS[ev.key] || Info;
  const sev = SEVERITY_STYLES[ev.severity] || SEVERITY_STYLES.unknown;
  const hasDeduction = (ev.deduction || 0) > 0;
  return (
    <div
      className="rounded-xl border border-border bg-foreground/[0.02] overflow-hidden"
      data-testid={`deduction-${ev.key}`}
    >
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 p-3 sm:p-4 text-left hover:bg-foreground/[0.03] transition-colors"
      >
        <div className={`h-9 w-9 rounded-lg border flex items-center justify-center ${hasDeduction ? "border-amber-500/30 bg-amber-500/10 text-amber-300" : "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"}`}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="text-sm font-medium truncate">{ev.label}</div>
            <StatBadge variant={sev.badge}>{sev.label}</StatBadge>
            <span className="text-[11px] text-muted-foreground">weight {ev.weight}</span>
          </div>
          <div className="mt-0.5 text-xs text-muted-foreground truncate">
            {ev.current_value != null ? <>Current: <span className="text-foreground/90 font-mono">{typeof ev.current_value === "number" ? `${ev.current_value}${ev.unit ? ` ${ev.unit}` : ""}` : String(ev.current_value)}</span></> : "No current reading"}
            {ev.normal_range && <> · Normal: <span className="text-foreground/70">{ev.normal_range}</span></>}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className={`text-sm font-semibold tabular-nums ${hasDeduction ? "text-red-300" : "text-emerald-300"}`} data-testid={`deduction-${ev.key}-value`}>
            {hasDeduction ? `−${ev.deduction} pts` : "0 pts"}
          </div>
          <div className="text-[10px] text-muted-foreground mt-0.5 flex items-center justify-end gap-1">
            details {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </div>
        </div>
      </button>
      {open && (
        <div className="px-3 sm:px-4 pb-3 sm:pb-4 pt-0 border-t border-border/50 bg-foreground/[0.015]">
          <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 text-xs mt-3">
            <div className="flex gap-2">
              <dt className="text-muted-foreground min-w-[110px]">Metric</dt>
              <dd className="font-medium">{ev.label}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-muted-foreground min-w-[110px]">Category</dt>
              <dd className="capitalize">{ev.category || "general"}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-muted-foreground min-w-[110px]">Current value</dt>
              <dd className="font-mono">{ev.current_value != null ? `${ev.current_value}${typeof ev.current_value === "number" && ev.unit ? ` ${ev.unit}` : ""}` : "—"}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-muted-foreground min-w-[110px]">Normal range</dt>
              <dd>{ev.normal_range || "—"}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-muted-foreground min-w-[110px]">Severity</dt>
              <dd className={sev.text}>{sev.label}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-muted-foreground min-w-[110px]">Points deducted</dt>
              <dd className={hasDeduction ? "text-red-300 font-semibold" : "text-emerald-300 font-semibold"}>
                {hasDeduction ? `${ev.deduction} of ${ev.weight}` : `0 of ${ev.weight}`}
              </dd>
            </div>
            {ev.reason && (
              <div className="md:col-span-2 flex gap-2">
                <dt className="text-muted-foreground min-w-[110px]">Reason</dt>
                <dd>{ev.reason}</dd>
              </div>
            )}
            {ev.recommendation && (
              <div className="md:col-span-2 flex gap-2">
                <dt className="text-muted-foreground min-w-[110px]">Recommendation</dt>
                <dd className="text-foreground/90">{ev.recommendation}</dd>
              </div>
            )}
          </dl>
        </div>
      )}
    </div>
  );
}

function MissingMetricRow({ ev }) {
  const Icon = METRIC_ICONS[ev.key] || Info;
  return (
    <div
      className="flex items-center gap-3 rounded-xl border border-dashed border-border bg-foreground/[0.015] p-3"
      data-testid={`missing-${ev.key}`}
    >
      <div className="h-9 w-9 rounded-lg border border-slate-500/25 bg-slate-500/10 text-slate-300 flex items-center justify-center">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium">{ev.label}</div>
        <div className="text-[11px] text-muted-foreground">
          Weight {ev.weight} · Normal: {ev.normal_range || "—"}
        </div>
      </div>
      <StatBadge variant="offline">No Data Available</StatBadge>
    </div>
  );
}

export function HealthAssessmentPanel({ deviceId, liveOverride }) {
  const [assessment, setAssessment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [timelineRange, setTimelineRange] = useState("24h");
  const [timeline, setTimeline] = useState([]);
  const [timelineLoading, setTimelineLoading] = useState(true);

  const loadAssessment = useCallback(async () => {
    try {
      setLoading(true);
      const r = await api.get(`/devices/${deviceId}/health`);
      setAssessment(r.data);
    } catch {
      setAssessment(null);
    } finally {
      setLoading(false);
    }
  }, [deviceId]);

  const loadTimeline = useCallback(async () => {
    try {
      setTimelineLoading(true);
      const r = await api.get(`/devices/${deviceId}/health/timeline?range=${timelineRange}&limit=1000`);
      setTimeline(r.data?.items || []);
    } catch {
      setTimeline([]);
    } finally {
      setTimelineLoading(false);
    }
  }, [deviceId, timelineRange]);

  useEffect(() => { loadAssessment(); }, [loadAssessment]);
  useEffect(() => { loadTimeline(); }, [loadTimeline]);

  // Merge live WebSocket updates from parent (optional).
  useEffect(() => {
    if (!liveOverride) return;
    setAssessment((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        score: liveOverride.score ?? prev.score,
        tier: liveOverride.tier ?? prev.tier,
        trend: liveOverride.trend ?? prev.trend,
        failure_risk_percent: liveOverride.failure_risk_percent ?? prev.failure_risk_percent,
        confidence_percent: liveOverride.confidence_percent ?? prev.confidence_percent,
        data_completeness_percent: liveOverride.data_completeness_percent ?? prev.data_completeness_percent,
      };
    });
    setTimeline((prev) => {
      if (!liveOverride.ts || liveOverride.score == null) return prev;
      const next = [...prev, {
        ts: liveOverride.ts,
        score: liveOverride.score,
        tier: liveOverride.tier,
        trend: liveOverride.trend,
        failure_risk_percent: liveOverride.failure_risk_percent,
        confidence_percent: liveOverride.confidence_percent,
        data_completeness_percent: liveOverride.data_completeness_percent,
      }];
      // Debounce: cap at 1000 points.
      return next.slice(-1000);
    });
  }, [liveOverride]);

  const chartData = useMemo(() => (timeline || []).map((p) => ({
    t: new Date(p.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    score: p.score,
    risk: p.failure_risk_percent,
    confidence: p.confidence_percent,
  })), [timeline]);

  const evaluated = useMemo(() => assessment?.evaluated_metrics || [], [assessment]);
  const missing = useMemo(() => assessment?.missing_metrics || [], [assessment]);
  const deductions = useMemo(() => [...evaluated].sort((a, b) => (b.deduction || 0) - (a.deduction || 0)), [evaluated]);
  const hasIssues = deductions.some((e) => (e.deduction || 0) > 0);
  const tierKey = assessment?.tier || "critical";
  const tier = TIER_META[tierKey] || TIER_META.critical;
  const trendKey = assessment?.trend || "unknown";
  const trend = TREND_META[trendKey] || TREND_META.unknown;
  const TrendIcon = trend.icon;

  if (loading) {
    return (
      <div className="rounded-2xl border border-border bg-card p-8 text-center flex items-center justify-center gap-3">
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
        <span className="text-sm text-muted-foreground">Computing health assessment…</span>
      </div>
    );
  }
  if (!assessment) {
    return <EmptyState title="No health data yet" description="The engine will compute a score as soon as the agent reports metrics." />;
  }

  return (
    <div className="space-y-4" data-testid="health-assessment-panel">
      {/* Headline: gauge + tier + trend + kpi cards */}
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(280px,360px),1fr] gap-4">
        <div className={`rounded-2xl border border-border bg-card p-5 flex items-center gap-5 ring-1 ring-inset ${tier.ring}`} data-testid="health-headline">
          <HealthGauge score={assessment.score} size={140} thickness={14} />
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <StatBadge variant={tier.tone} testId="health-tier-badge">{tier.label}</StatBadge>
              <span className="inline-flex items-center gap-1 rounded-full border border-border bg-foreground/[0.03] px-2 py-0.5 text-[11px]" data-testid="health-trend-chip">
                <TrendIcon className={`h-3 w-3 ${trend.className}`} />
                <span className={trend.className}>{trend.label}</span>
              </span>
              <LiveIndicator />
            </div>
            <div className="mt-2 text-sm text-muted-foreground max-w-xs">
              {hasIssues
                ? "The engine identified factors reducing this device's health."
                : "All evaluated metrics are within normal ranges."}
            </div>
            <div className="mt-2 text-[11px] text-muted-foreground font-mono">
              engine {assessment.engine_version}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <Kpi label="Health Score" value={<>{assessment.score}<span className="text-base text-muted-foreground">/100</span></>} hint={tier.label} testId="kpi-health-score" tone={tierKey === "excellent" || tierKey === "good" ? "good" : tierKey === "warning" ? "warn" : "critical"} />
          <Kpi label="Failure Risk" value={`${assessment.failure_risk_percent}%`} hint={assessment.failure_risk_percent >= 40 ? "Elevated — investigate" : "Within tolerance"} testId="kpi-failure-risk" tone={assessment.failure_risk_percent >= 40 ? "critical" : assessment.failure_risk_percent >= 20 ? "warn" : "default"} />
          <Kpi label="Confidence" value={`${assessment.confidence_percent}%`} hint={assessment.confidence_percent >= 80 ? "High confidence" : assessment.confidence_percent >= 50 ? "Moderate" : "Low — need more signals"} testId="kpi-confidence" tone={assessment.confidence_percent >= 80 ? "info" : "default"} />
          <Kpi label="Data Completeness" value={`${assessment.data_completeness_percent}%`} hint={`${evaluated.length}/${evaluated.length + missing.length} metrics evaluated`} testId="kpi-completeness" tone={assessment.data_completeness_percent >= 80 ? "good" : assessment.data_completeness_percent >= 50 ? "default" : "warn"} />
        </div>
      </div>

      {/* Deduction breakdown */}
      <div className="rounded-2xl border border-border bg-card p-4 sm:p-5">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
          <div className="flex items-center gap-2">
            {hasIssues ? <AlertTriangle className="h-4 w-4 text-amber-400" /> : <CheckCircle2 className="h-4 w-4 text-emerald-400" />}
            <div className="text-sm font-semibold">Score breakdown — {hasIssues ? "why points were deducted" : "no deductions"}</div>
          </div>
          <div className="text-[11px] text-muted-foreground">
            Total deduction: <span className="font-semibold text-foreground">−{assessment.total_deduction} pts</span>
            <span className="mx-1">·</span>
            Evaluated weight: <span className="font-semibold text-foreground">{assessment.total_weight_evaluated}/100</span>
          </div>
        </div>
        <div className="space-y-2" data-testid="deductions-list">
          {deductions.map((ev, i) => (
            <DeductionRow key={ev.key} ev={ev} defaultOpen={i === 0 && (ev.deduction || 0) > 0} />
          ))}
        </div>
      </div>

      {/* Missing metrics */}
      {missing.length > 0 && (
        <div className="rounded-2xl border border-border bg-card p-4 sm:p-5" data-testid="missing-metrics-panel">
          <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-slate-300" />
              <div className="text-sm font-semibold">Not evaluated — awaiting data</div>
            </div>
            <div className="text-[11px] text-muted-foreground">
              These metrics are ignored (no deduction, no redistribution) until the agent supplies data.
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {missing.map((ev) => <MissingMetricRow key={ev.key} ev={ev} />)}
          </div>
        </div>
      )}

      {/* Timeline */}
      <div className="rounded-2xl border border-border bg-card p-4 sm:p-5" data-testid="health-timeline-panel">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            <div className="text-sm font-semibold">Health timeline</div>
            {timelineLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          </div>
          <div className="flex items-center gap-1 rounded-full border border-border bg-foreground/[0.03] p-1">
            {RANGES.map((r) => (
              <button
                key={r.key}
                onClick={() => setTimelineRange(r.key)}
                data-testid={`health-range-${r.key}`}
                className={`h-7 px-3 text-[11px] rounded-full transition-colors ${timelineRange === r.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>
        {chartData.length === 0 ? (
          <div className="h-56 rounded-xl border border-dashed border-border flex items-center justify-center text-xs text-muted-foreground">
            No historical health data yet — snapshots are stored as telemetry arrives.
          </div>
        ) : (
          <div className="h-56" data-testid="health-timeline-chart">
            <ResponsiveContainer>
              <LineChart data={chartData} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.4} />
                <XAxis dataKey="t" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} minTickGap={30} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} width={30} />
                <Tooltip contentStyle={{ background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 10, fontSize: 12 }} />
                <ReferenceLine y={90} stroke="rgb(52, 211, 153)" strokeDasharray="3 3" opacity={0.35} />
                <ReferenceLine y={75} stroke="rgb(163, 230, 53)" strokeDasharray="3 3" opacity={0.3} />
                <ReferenceLine y={50} stroke="rgb(251, 191, 36)" strokeDasharray="3 3" opacity={0.3} />
                <Line type="monotone" dataKey="score" name="Health" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="risk" name="Failure Risk" stroke="rgb(248, 113, 113)" strokeWidth={1.5} dot={false} isAnimationActive={false} strokeDasharray="4 3" />
                <Line type="monotone" dataKey="confidence" name="Confidence" stroke="rgb(103, 232, 249)" strokeWidth={1} dot={false} isAnimationActive={false} opacity={0.5} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        <div className="mt-2 text-[11px] text-muted-foreground flex items-center gap-3 flex-wrap">
          <span className="inline-flex items-center gap-1"><span className="h-2 w-3 rounded bg-primary" /> Health</span>
          <span className="inline-flex items-center gap-1"><span className="h-2 w-3 rounded bg-red-400/70" /> Failure risk</span>
          <span className="inline-flex items-center gap-1"><span className="h-2 w-3 rounded bg-cyan-300/50" /> Confidence</span>
          <span className="ml-auto text-[10px]">Dashed lines: Excellent (90) · Good (75) · Warning (50)</span>
        </div>
      </div>

      <div className="text-[11px] text-muted-foreground flex items-start gap-2">
        <ShieldCheck className="h-3.5 w-3.5 mt-0.5 text-emerald-400 shrink-0" />
        <span>
          This assessment is transparent: every deduction is explained above.
          The engine is modular — future versions (ML tuning, AI-generated recommendations) will slot in
          behind this same API without any UI changes.
        </span>
      </div>
    </div>
  );
}
