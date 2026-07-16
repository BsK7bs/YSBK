import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft, Cpu, MemoryStick, Thermometer, Wifi, HardDrive, Power, Lock, RotateCcw,
  RefreshCw, Trash2, Server, Package, BellRing, Activity, Sparkles, History, Loader2,
  Users as UsersIcon, ScrollText, Zap, TrendingUp, TrendingDown, Lightbulb, ChevronRight,
  Globe, Database, Radio, Wrench,
} from "lucide-react";
import { toast } from "sonner";
import { motion } from "framer-motion";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend, Area, AreaChart } from "recharts";
import { api } from "../lib/api";
import { useDashboardSocket } from "../contexts/WebSocketContext";
import { OnlineBadge, RiskBadge, StatBadge } from "../components/StatBadge";
import { HealthGauge } from "../components/HealthGauge";
import { HealthAssessmentPanel } from "../components/HealthAssessmentPanel";
import { PredictionPanel } from "../components/PredictionPanel";
import { RemoteManagementPanel } from "../components/RemoteManagementPanel";
import { LiveIndicator } from "../components/LiveIndicator";
import { EmptyState } from "../components/EmptyState";
import { MaintenanceDialog, MaintenanceBadge } from "../components/MaintenanceDialog";
import AgentDiagnosticsPanel from "../components/AgentDiagnosticsPanel";
import { formatRelative, hasRole, severityColor, extractError } from "../lib/format";
import { useAuth } from "../contexts/AuthContext";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "../components/ui/alert-dialog";
import { Button } from "../components/ui/button";

const RANGES = [
  { label: "1h", minutes: 60 },
  { label: "6h", minutes: 360 },
  { label: "24h", minutes: 1440 },
  { label: "7d", minutes: 10080 },
];

// ---- helpers ----
function MetricTile({ icon: Icon, label, value, unit, testId, hint, tone = "default" }) {
  const toneStyle = {
    default: "text-primary bg-primary/10 border-primary/25",
    warning: "text-amber-300 bg-amber-500/10 border-amber-500/25",
    critical: "text-red-300 bg-red-500/10 border-red-500/25",
    success: "text-emerald-300 bg-emerald-500/10 border-emerald-500/25",
    info: "text-cyan-300 bg-cyan-500/10 border-cyan-500/25",
  }[tone] || "text-primary bg-primary/10 border-primary/25";
  return (
    <div className="rounded-2xl border border-border bg-card p-4 sm:p-5 card-hover" data-testid={testId}>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <div className={`h-7 w-7 rounded-lg border flex items-center justify-center ${toneStyle}`}><Icon className="h-3.5 w-3.5" /></div>
        <span className="uppercase tracking-widest">{label}</span>
      </div>
      <div className="mt-2 text-2xl font-semibold tabular-nums" data-testid={`${testId}-value`}>
        {value == null ? "—" : value}{value != null && unit && <span className="ml-1 text-sm text-muted-foreground">{unit}</span>}
      </div>
      {hint && <div className="text-[11px] text-muted-foreground mt-1">{hint}</div>}
    </div>
  );
}

function ChartCard({ title, data, dataKey, color, unit, domain, height = 220, testId, series }) {
  const hasData = data && data.length > 0;
  return (
    <div className="rounded-2xl border border-border bg-card p-4 sm:p-5" data-testid={testId}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-semibold">{title}</div>
        <LiveIndicator />
      </div>
      {!hasData ? (
        <div className="rounded-xl border border-dashed border-border" style={{ height }}>
          <div className="h-full flex items-center justify-center text-xs text-muted-foreground">Waiting for telemetry…</div>
        </div>
      ) : (
        <div style={{ height }}>
          <ResponsiveContainer>
            <AreaChart data={data} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={`g-${testId}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
              <XAxis dataKey="t" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} minTickGap={30} />
              <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} domain={domain || ["auto", "auto"]} width={34} />
              <Tooltip contentStyle={{ background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 10, fontSize: 12 }} />
              {series ? series.map((s) => (
                <Area key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2} fill={s.fill || "transparent"} isAnimationActive={false} />
              )) : (
                <Area type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} fill={`url(#g-${testId})`} isAnimationActive={false} />
              )}
              {series && <Legend wrapperStyle={{ fontSize: 11 }} />}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function ActionButton({ icon: Icon, label, kind, deviceId, onQueued, destructive = false }) {
  const [loading, setLoading] = useState(false);
  const doAction = async () => {
    setLoading(true);
    try {
      await api.post(`/actions/devices/${deviceId}`, { kind, params: {} });
      toast.success(`Queued: ${label}`);
      onQueued?.();
    } catch (e) {
      toast.error(extractError(e, `Failed to queue ${label}`));
    } finally {
      setLoading(false);
    }
  };
  if (!destructive) {
    return (
      <button onClick={doAction} disabled={loading} data-testid={`action-${kind}`} className="flex items-center gap-2 h-10 px-3 rounded-xl border border-border bg-foreground/[0.03] hover:bg-foreground/[0.06] text-sm">
        {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4" />} {label}
      </button>
    );
  }
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <button data-testid={`action-${kind}`} className="flex items-center gap-2 h-10 px-3 rounded-xl border border-red-500/30 bg-red-500/10 hover:bg-red-500/15 text-sm text-red-300">
          <Icon className="h-4 w-4" />{label}
        </button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Confirm {label.toLowerCase()}</AlertDialogTitle>
          <AlertDialogDescription>The desktop agent will pick up this action on its next check-in. Logged in the audit trail.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={doAction} data-testid={`action-${kind}-confirm`}>{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Confirm"}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ---- Recommendations engine (rule-based) ----
function computeRecommendations(device, alerts, actions) {
  const recs = [];
  const m = device?.latest_metrics || {};
  const inv = device?.inventory || {};
  if (!device?.is_online) recs.push({ level: "critical", title: "Device is offline", body: "The agent is not reporting. Verify power, network, and that the DigitalTwinAgent service is running." });
  if (typeof m.cpu_percent === "number" && m.cpu_percent >= 90) recs.push({ level: "critical", title: "Sustained high CPU", body: "CPU is above 90 %. Investigate top processes and consider terminating runaway tasks." });
  else if (typeof m.cpu_percent === "number" && m.cpu_percent >= 75) recs.push({ level: "warning", title: "Elevated CPU usage", body: "CPU has been running hot. Review scheduled tasks or background scans." });
  if (typeof m.ram_percent === "number" && m.ram_percent >= 90) recs.push({ level: "critical", title: "Memory pressure", body: "RAM usage is above 90 %. Close heavy apps or plan a memory upgrade." });
  if (typeof m.disk_percent === "number" && m.disk_percent >= 90) recs.push({ level: "critical", title: "Disk almost full", body: "Free up space or expand the disk. Consider running 'Clear temp files' from Remote Actions." });
  else if (typeof m.disk_percent === "number" && m.disk_percent >= 80) recs.push({ level: "warning", title: "Disk nearing capacity", body: "Below 20 % free space. Plan cleanup before it becomes critical." });
  if (typeof m.cpu_temp_c === "number" && m.cpu_temp_c >= 85) recs.push({ level: "critical", title: "Thermal throttling risk", body: "CPU temperature above 85 °C. Check fans, dust, and thermal paste." });
  else if (typeof m.cpu_temp_c === "number" && m.cpu_temp_c >= 75) recs.push({ level: "warning", title: "Running warm", body: "CPU temperature is elevated. Ensure ventilation is unobstructed." });
  if (typeof m.ram_percent === "number" && m.ram_percent >= 60 && typeof m.swap_percent === "number" && m.swap_percent >= 40) recs.push({ level: "warning", title: "Heavy swap usage", body: "Swap is being used significantly — the system may feel sluggish. Adding RAM would help." });
  const smart = m.smart || inv.disk?.smart || [];
  if (Array.isArray(smart)) {
    smart.forEach((d) => { if (d && d.assessment && d.assessment !== "PASS") recs.push({ level: "critical", title: `Disk SMART: ${d.name || d.model}`, body: `SMART reports ${d.assessment}. Back up immediately and replace the drive soon.` }); });
  }
  if (typeof device?.health_score === "number" && device.health_score < 60) recs.push({ level: "warning", title: "Low health score", body: "Overall device health is below 60. Review the recent alerts and consider a maintenance action." });
  const openAlerts = (alerts || []).filter((a) => !a.resolved_at).length;
  if (openAlerts >= 3) recs.push({ level: "warning", title: `${openAlerts} unresolved alerts`, body: "Multiple alerts are still open. Acknowledge and resolve to keep the audit trail clean." });
  const inv_sw = inv.installed_software || inv.installed_software?.items;
  const sw_count = Array.isArray(inv_sw) ? inv_sw.length : 0;
  if (sw_count > 800) recs.push({ level: "info", title: "Large installed-software footprint", body: `${sw_count} apps detected. Audit for unused programs to reduce attack surface.` });
  if (recs.length === 0) recs.push({ level: "success", title: "All clear", body: "No recommendations right now — the device looks healthy." });
  return recs;
}

// ---- Predicted health score (simple linear regression over recent telemetry) ----
function predictHealth(telemetry) {
  if (!telemetry || telemetry.length < 3) return null;
  const points = telemetry
    .map((t) => t.metrics || {})
    .filter((m) => typeof m.cpu_percent === "number" && typeof m.ram_percent === "number")
    .map((m, i) => {
      let s = 100 - Math.max(0, (m.cpu_percent || 0) - 60) * 0.6 - Math.max(0, (m.ram_percent || 0) - 60) * 0.6 - Math.max(0, (m.disk_percent || 0) - 70) * 0.8 - Math.max(0, (m.cpu_temp_c || 0) - 70) * 0.7;
      return { x: i, y: Math.max(0, Math.min(100, s)) };
    });
  if (points.length < 3) return null;
  const n = points.length;
  const sumX = points.reduce((s, p) => s + p.x, 0);
  const sumY = points.reduce((s, p) => s + p.y, 0);
  const sumXY = points.reduce((s, p) => s + p.x * p.y, 0);
  const sumX2 = points.reduce((s, p) => s + p.x * p.x, 0);
  const slope = (n * sumXY - sumX * sumY) / Math.max(1e-6, n * sumX2 - sumX * sumX);
  const intercept = (sumY - slope * sumX) / n;
  const currentIdx = points[points.length - 1].x;
  const forecast60 = Math.max(0, Math.min(100, slope * (currentIdx + Math.min(60, points.length)) + intercept));
  return {
    slope,
    trend: slope > 0.1 ? "improving" : slope < -0.1 ? "declining" : "stable",
    forecast60: Math.round(forecast60),
    samples: n,
  };
}

// ---- Main component ----
export default function DeviceDetailPage() {
  const { deviceId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get("tab") || "overview";
  const setActiveTab = (v) => {
    const next = new URLSearchParams(searchParams);
    if (v && v !== "overview") next.set("tab", v);
    else next.delete("tab");
    setSearchParams(next, { replace: true });
  };
  const { user } = useAuth();
  const { subscribe } = useDashboardSocket();

  const [device, setDevice] = useState(null);
  const [telemetry, setTelemetry] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [actions, setActions] = useState([]);
  const [audit, setAudit] = useState([]);
  const [range, setRange] = useState(60);
  const [notFound, setNotFound] = useState(false);
  const [liveHealth, setLiveHealth] = useState(null);

  const loadAll = useCallback(async () => {
    try {
      const [d, t, a, ac] = await Promise.all([
        api.get(`/devices/${deviceId}`),
        api.get(`/devices/${deviceId}/telemetry?minutes=${range}&limit=500`),
        api.get(`/alerts?device_id=${deviceId}&limit=100`),
        api.get(`/actions?device_id=${deviceId}&limit=100`),
      ]);
      setDevice(d.data);
      setTelemetry(t.data || []);
      setAlerts(a.data || []);
      setActions(ac.data || []);
    } catch (e) {
      if (e?.response?.status === 404) setNotFound(true);
    }
    if (hasRole(user, "admin")) {
      try {
        const au = await api.get("/audit?limit=100");
        setAudit((au.data || []).filter((x) => x.target === deviceId || (x.metadata || {}).hostname === deviceId));
      } catch {}
    }
  }, [deviceId, range, user]);

  useEffect(() => { loadAll(); }, [loadAll]);

  useEffect(() => {
    return subscribe((msg) => {
      if (msg.device_id && msg.device_id !== deviceId) return;
      if (msg.type === "telemetry") {
        setDevice((prev) => prev ? { ...prev, latest_metrics: { ...(prev.latest_metrics || {}), ...(msg.metrics || {}) }, health_score: msg.health_score ?? prev.health_score, risk_level: msg.risk_level ?? prev.risk_level, last_seen: msg.ts, is_online: true } : prev);
        setTelemetry((prev) => [...prev, { ts: msg.ts, metrics: msg.metrics || {} }].slice(-500));
        if (msg.health) {
          setLiveHealth({ ...msg.health, ts: msg.ts });
        }
      } else if (msg.type === "device.online" || msg.type === "device.offline") {
        setDevice((prev) => prev ? { ...prev, is_online: msg.type === "device.online" } : prev);
      } else if (msg.type === "inventory") {
        api.get(`/devices/${deviceId}`).then((r) => setDevice(r.data)).catch(() => {});
      } else if (msg.type === "alerts") {
        api.get(`/alerts?device_id=${deviceId}&limit=100`).then((r) => setAlerts(r.data || [])).catch(() => {});
      }
    });
  }, [subscribe, deviceId]);

  const chartData = useMemo(() => telemetry.filter((t) => t.metrics).map((t) => ({
    t: new Date(t.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    cpu: t.metrics.cpu_percent, ram: t.metrics.ram_percent, disk: t.metrics.disk_percent,
    temp: t.metrics.cpu_temp_c, up: t.metrics.net_up_kbps, down: t.metrics.net_down_kbps,
    swap: t.metrics.swap_percent, gpu: (t.metrics.gpus && t.metrics.gpus[0]?.utilization_percent) || null,
    gpu_temp: (t.metrics.gpus && t.metrics.gpus[0]?.temperature_c) || null,
  })), [telemetry]);

  const timeline = useMemo(() => {
    const items = [];
    (actions || []).forEach((a) => items.push({ ts: a.created_at, kind: "action", severity: a.status === "failed" ? "critical" : "info", title: `Action ${a.kind}`, subtitle: `${a.status}${a.error ? " — " + a.error : ""}` }));
    (alerts || []).forEach((a) => items.push({ ts: a.ts, kind: "alert", severity: a.severity, title: a.message, subtitle: a.kind }));
    (audit || []).forEach((e) => items.push({ ts: e.ts, kind: "audit", severity: "info", title: e.kind, subtitle: e.actor_email || "system" }));
    return items.sort((a, b) => new Date(b.ts) - new Date(a.ts)).slice(0, 100);
  }, [actions, alerts, audit]);

  const prediction = useMemo(() => predictHealth(telemetry), [telemetry]);
  const recommendations = useMemo(() => computeRecommendations(device, alerts, actions), [device, alerts, actions]);

  const canTech = hasRole(user, "technician");
  const canAdmin = hasRole(user, "admin");
  const [maintOpen, setMaintOpen] = useState(false);

  if (notFound) {
    return (
      <div className="rounded-2xl border border-border bg-card p-8 text-center">
        <div className="text-lg font-semibold">Device not found</div>
        <div className="mt-1 text-sm text-muted-foreground">It may have been removed or belongs to another organization.</div>
        <button onClick={() => navigate("/app/devices")} className="mt-4 inline-flex items-center gap-2 text-primary text-sm"><ArrowLeft className="h-4 w-4" /> Back to devices</button>
      </div>
    );
  }
  if (!device) {
    return (
      <div className="space-y-4">
        <div className="h-24 rounded-2xl border border-border bg-card animate-pulse" />
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-24 rounded-2xl border border-border bg-card animate-pulse" />)}</div>
        <div className="h-72 rounded-2xl border border-border bg-card animate-pulse" />
      </div>
    );
  }

  const m = device.latest_metrics || {};
  const inv = device.inventory || {};
  const sysInv = inv.system || {};
  const procs = inv.processes || {};
  const services = inv.services || {};
  const events = inv.events || {};
  const usbInv = inv.usb_devices || {};
  const printers = inv.printers || {};
  const monitors = inv.monitors || {};
  const gpuList = Array.isArray(m.gpus) && m.gpus.length ? m.gpus : (Array.isArray(inv.gpu?.gpus) ? inv.gpu.gpus : []);
  const partitions = (inv.disk?.partitions) || m.partitions || [];
  const smartList = (m.smart) || (inv.disk?.smart) || [];
  const adapters = m.adapters || inv.network?.adapters || [];
  const users = sysInv.logged_users || (sysInv.logged_user ? [sysInv.logged_user] : []);

  const removeDevice = async () => {
    try { await api.delete(`/devices/${deviceId}`); toast.success("Device removed"); navigate("/app/devices"); }
    catch (e) { toast.error(extractError(e, "Failed to remove")); }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <button onClick={() => navigate("/app/devices")} className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 mb-2"><ArrowLeft className="h-3 w-3" /> Back to devices</button>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="text-2xl font-semibold tracking-tight truncate max-w-[420px]" data-testid="twin-device-name">{device.display_name || device.hostname}</div>
            <OnlineBadge online={device.is_online} />
            <RiskBadge risk={device.is_online ? device.risk_level : "offline"} />
            {device.has_agent && <StatBadge variant="healthy">Agent v{device.agent_version || "?"}</StatBadge>}
            {device.created_via === "manual" && <StatBadge variant="info">Manually registered</StatBadge>}
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            {device.os_name || "Unknown OS"} {device.os_version || ""} · host <span className="font-mono">{device.hostname}</span>
            {device.ip_address && <> · <span className="font-mono">{device.ip_address}</span></>}
            · last seen {formatRelative(device.last_seen)}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <MaintenanceBadge device={device} />
          <LiveIndicator />
          <button onClick={loadAll} className="h-10 px-3 rounded-xl border border-border bg-foreground/[0.03] hover:bg-foreground/[0.06] text-sm flex items-center gap-2"><RefreshCw className="h-4 w-4" /> Refresh</button>
          {canTech && (
            <button onClick={() => setMaintOpen(true)} data-testid="maintenance-toggle-btn"
              className={`h-10 px-3 rounded-xl border text-sm flex items-center gap-2 ${device.maintenance_mode ? "border-amber-500/40 bg-amber-500/10 text-amber-200 hover:bg-amber-500/15" : "border-border bg-foreground/[0.03] hover:bg-foreground/[0.06]"}`}>
              <Wrench className="h-4 w-4" /> {device.maintenance_mode ? "In Maintenance" : "Maintenance"}
            </button>
          )}
          {canAdmin && (
            <AlertDialog>
              <AlertDialogTrigger asChild><button data-testid="remove-device-button" className="h-10 px-3 rounded-xl border border-red-500/30 bg-red-500/10 hover:bg-red-500/15 text-sm text-red-300 flex items-center gap-2"><Trash2 className="h-4 w-4" /> Remove</button></AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader><AlertDialogTitle>Remove this device?</AlertDialogTitle><AlertDialogDescription>Revokes the agent's API key and deletes all its telemetry, alerts, and actions.</AlertDialogDescription></AlertDialogHeader>
                <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={removeDevice} data-testid="remove-device-confirm">Remove</AlertDialogAction></AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </div>

      <MaintenanceDialog open={maintOpen} onOpenChange={setMaintOpen} device={device} onChanged={loadAll} />

      {/* Quick tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
        <div className="rounded-2xl border border-border bg-card p-4 flex flex-col items-center justify-center">
          <HealthGauge score={device.health_score} size={90} thickness={8} />
        </div>
        <MetricTile icon={Cpu} label="CPU" value={m.cpu_percent != null ? m.cpu_percent.toFixed(0) : null} unit="%" testId="tile-cpu" tone={m.cpu_percent >= 90 ? "critical" : m.cpu_percent >= 75 ? "warning" : "default"} />
        <MetricTile icon={MemoryStick} label="RAM" value={m.ram_percent != null ? m.ram_percent.toFixed(0) : null} unit="%" testId="tile-ram" tone={m.ram_percent >= 90 ? "critical" : m.ram_percent >= 75 ? "warning" : "default"} />
        <MetricTile icon={HardDrive} label="Disk" value={m.disk_percent != null ? m.disk_percent.toFixed(0) : null} unit="%" testId="tile-disk" tone={m.disk_percent >= 90 ? "critical" : m.disk_percent >= 80 ? "warning" : "default"} />
        <MetricTile icon={Thermometer} label="Temp" value={m.cpu_temp_c != null ? m.cpu_temp_c.toFixed(0) : null} unit="°C" testId="tile-temp" tone={m.cpu_temp_c >= 85 ? "critical" : m.cpu_temp_c >= 75 ? "warning" : "default"} />
        <MetricTile icon={Wifi} label="Network" value={m.net_down_kbps != null ? Math.round((m.net_down_kbps || 0) + (m.net_up_kbps || 0)).toLocaleString() : null} unit="kbps" testId="tile-net" hint={m.latency_ms != null ? `${m.latency_ms} ms latency` : null} />
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="flex-wrap gap-1 h-auto">
          <TabsTrigger value="overview" data-testid="tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="charts" data-testid="tab-charts">Live Charts</TabsTrigger>
          <TabsTrigger value="hardware">Hardware</TabsTrigger>
          <TabsTrigger value="software">Software</TabsTrigger>
          <TabsTrigger value="processes">Processes</TabsTrigger>
          <TabsTrigger value="network">Network</TabsTrigger>
          <TabsTrigger value="users">Users</TabsTrigger>
          <TabsTrigger value="events">Event Logs</TabsTrigger>
          <TabsTrigger value="alerts" data-testid="tab-alerts">Alerts</TabsTrigger>
          <TabsTrigger value="health" data-testid="tab-health">Health & Prediction</TabsTrigger>
          <TabsTrigger value="ai-prediction" data-testid="tab-ai-prediction">AI Prediction</TabsTrigger>
          <TabsTrigger value="remote" data-testid="tab-remote">Remote</TabsTrigger>
          <TabsTrigger value="maintenance" data-testid="tab-maintenance">Maintenance</TabsTrigger>
          <TabsTrigger value="diagnostics" data-testid="tab-diagnostics">Diagnostics</TabsTrigger>
          <TabsTrigger value="recommendations" data-testid="tab-recs">Recommendations</TabsTrigger>
        </TabsList>

        {/* OVERVIEW */}
        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="rounded-2xl border border-border bg-card p-5">
              <div className="text-sm font-semibold mb-2 flex items-center gap-2"><Server className="h-4 w-4 text-primary" /> Identity</div>
              <dl className="text-sm grid grid-cols-[120px,1fr] gap-y-1.5">
                <dt className="text-muted-foreground">Hostname</dt><dd className="font-mono truncate">{device.hostname}</dd>
                <dt className="text-muted-foreground">OS</dt><dd>{device.os_name || "—"} {device.os_version || ""}</dd>
                <dt className="text-muted-foreground">Serial</dt><dd className="font-mono truncate">{device.serial_number || "—"}</dd>
                <dt className="text-muted-foreground">IP</dt><dd className="font-mono">{device.ip_address || "—"}</dd>
                <dt className="text-muted-foreground">MAC</dt><dd className="font-mono">{device.mac_address || "—"}</dd>
              </dl>
            </div>
            <div className="rounded-2xl border border-border bg-card p-5">
              <div className="text-sm font-semibold mb-2 flex items-center gap-2"><Cpu className="h-4 w-4 text-primary" /> Compute</div>
              <dl className="text-sm grid grid-cols-[120px,1fr] gap-y-1.5">
                <dt className="text-muted-foreground">CPU</dt><dd className="truncate">{device.cpu || sysInv.cpu_model || "—"}</dd>
                <dt className="text-muted-foreground">Cores</dt><dd className="tabular-nums">{m.cpu_count ?? sysInv.cpu_cores ?? "—"} phys / {m.cpu_count_logical ?? "—"} log</dd>
                <dt className="text-muted-foreground">RAM</dt><dd className="tabular-nums">{device.ram_gb != null ? `${device.ram_gb} GB` : "—"}</dd>
                <dt className="text-muted-foreground">Disk</dt><dd className="tabular-nums">{device.disk_gb != null ? `${Math.round(device.disk_gb)} GB total` : "—"}</dd>
                <dt className="text-muted-foreground">Motherboard</dt><dd className="truncate">{device.motherboard || "—"}</dd>
                <dt className="text-muted-foreground">BIOS</dt><dd className="truncate">{device.bios_version || "—"}</dd>
              </dl>
            </div>
            <div className="rounded-2xl border border-border bg-card p-5">
              <div className="text-sm font-semibold mb-2 flex items-center gap-2"><Activity className="h-4 w-4 text-primary" /> Runtime</div>
              <dl className="text-sm grid grid-cols-[120px,1fr] gap-y-1.5">
                <dt className="text-muted-foreground">Boot time</dt><dd className="truncate">{sysInv.boot_time ? new Date(sysInv.boot_time).toLocaleString() : "—"}</dd>
                <dt className="text-muted-foreground">Uptime</dt><dd className="tabular-nums">{sysInv.uptime_sec ? `${Math.round(sysInv.uptime_sec / 3600)} h` : "—"}</dd>
                <dt className="text-muted-foreground">Timezone</dt><dd>{sysInv.timezone || "—"}</dd>
                <dt className="text-muted-foreground">Logged user</dt><dd className="truncate">{sysInv.logged_user || "—"}</dd>
                <dt className="text-muted-foreground">Load avg</dt><dd className="tabular-nums">{Array.isArray(m.load_avg_1_5_15) ? m.load_avg_1_5_15.map((v) => v.toFixed(2)).join(" · ") : "—"}</dd>
                <dt className="text-muted-foreground">Agent</dt><dd>{device.has_agent ? `v${device.agent_version || "?"}` : "not enrolled"}</dd>
              </dl>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <ChartCard title="CPU & RAM (live)" data={chartData} testId="ov-cpu-ram" color="hsl(var(--primary))" domain={[0, 100]} series={[
              { key: "cpu", name: "CPU %", color: "hsl(var(--primary))" }, { key: "ram", name: "RAM %", color: "hsl(var(--info))" },
            ]} />
            <ChartCard title="Disk & Temperature (live)" data={chartData} testId="ov-disk-temp" color="hsl(var(--warning))" domain={[0, 100]} series={[
              { key: "disk", name: "Disk %", color: "hsl(var(--chart-3))" }, { key: "temp", name: "Temp °C", color: "hsl(var(--warning))" },
            ]} />
          </div>
        </TabsContent>

        {/* CHARTS */}
        <TabsContent value="charts" className="mt-4">
          <div className="rounded-2xl border border-border bg-card p-4 sm:p-5 mb-4">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <div className="text-sm font-semibold">Live performance charts</div>
                <div className="text-xs text-muted-foreground">Streaming from the desktop agent</div>
              </div>
              <div className="flex items-center rounded-xl border border-border p-0.5" data-testid="time-range-selector">
                {RANGES.map((r) => (
                  <button key={r.label} onClick={() => setRange(r.minutes)} className={`px-3 h-8 rounded-lg text-xs font-medium ${range === r.minutes ? "bg-foreground/10 text-foreground" : "text-muted-foreground hover:text-foreground"}`}>{r.label}</button>
                ))}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            <ChartCard title="CPU %" data={chartData} dataKey="cpu" color="hsl(var(--primary))" domain={[0, 100]} testId="chart-cpu-full" />
            <ChartCard title="RAM %" data={chartData} dataKey="ram" color="hsl(var(--info))" domain={[0, 100]} testId="chart-ram-full" />
            <ChartCard title="Disk %" data={chartData} dataKey="disk" color="hsl(var(--chart-3))" domain={[0, 100]} testId="chart-disk-full" />
            <ChartCard title="Temperature °C" data={chartData} dataKey="temp" color="hsl(var(--warning))" testId="chart-temp-full" />
            <ChartCard title="Network (up/down kbps)" data={chartData} testId="chart-net-full" color="hsl(var(--chart-2))" series={[
              { key: "down", name: "Down kbps", color: "hsl(var(--chart-2))" }, { key: "up", name: "Up kbps", color: "hsl(var(--chart-4))" },
            ]} />
            <ChartCard title="GPU % / Temp" data={chartData} testId="chart-gpu-full" color="hsl(var(--chart-5))" series={[
              { key: "gpu", name: "GPU util %", color: "hsl(var(--chart-5))" }, { key: "gpu_temp", name: "GPU temp °C", color: "hsl(var(--warning))" },
            ]} />
          </div>
        </TabsContent>

        {/* HARDWARE */}
        <TabsContent value="hardware" className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-2xl border border-border bg-card p-5">
              <div className="text-sm font-semibold mb-3">Storage</div>
              {partitions.length === 0 ? <div className="text-sm text-muted-foreground">No partition data yet.</div> : (
                <ul className="space-y-2 text-sm">
                  {partitions.map((p, i) => (
                    <li key={i} className="rounded-xl border border-border p-3">
                      <div className="flex items-center justify-between gap-3">
                        <div><div className="font-mono">{p.device || p.name}</div><div className="text-xs text-muted-foreground">{p.mountpoint} · {p.fstype || p.type || "disk"}</div></div>
                        <div className="tabular-nums text-right"><div>{p.used_gb != null ? `${p.used_gb} / ${p.total_gb} GB` : `${p.total_gb || "—"} GB`}</div><div className={`text-xs ${p.percent >= 90 ? "text-red-400" : p.percent >= 80 ? "text-amber-400" : "text-muted-foreground"}`}>{p.percent != null ? `${p.percent}% used` : ""}</div></div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rounded-2xl border border-border bg-card p-5">
              <div className="text-sm font-semibold mb-3">SMART / Disk health</div>
              {smartList.length === 0 ? <div className="text-sm text-muted-foreground">SMART not available on this device (install <span className="font-mono">smartctl</span> to enable).</div> : (
                <ul className="space-y-2 text-sm">
                  {smartList.map((d, i) => (
                    <li key={i} className="rounded-xl border border-border p-3 flex items-center justify-between gap-3">
                      <div><div className="font-medium">{d.model || d.name}</div><div className="text-xs text-muted-foreground">{d.name} · {d.interface || ""} {d.is_ssd ? "· SSD" : ""}</div></div>
                      <StatBadge variant={d.assessment === "PASS" ? "healthy" : d.assessment ? "critical" : "info"}>{d.assessment || "unknown"}</StatBadge>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rounded-2xl border border-border bg-card p-5">
              <div className="text-sm font-semibold mb-3">GPUs</div>
              {gpuList.length === 0 ? <div className="text-sm text-muted-foreground">No discrete GPU reported.</div> : (
                <ul className="space-y-2 text-sm">
                  {gpuList.map((g, i) => (
                    <li key={i} className="rounded-xl border border-border p-3">
                      <div className="flex items-center justify-between"><div className="font-medium truncate">{g.name}</div><div className="text-xs text-muted-foreground">{g.vendor}</div></div>
                      <div className="text-xs text-muted-foreground mt-1 tabular-nums">Util {g.utilization_percent != null ? `${Math.round(g.utilization_percent)}%` : "—"} · Mem {g.memory_used_mb != null ? `${Math.round(g.memory_used_mb)}/${Math.round(g.memory_total_mb)} MB` : "—"} · Temp {g.temperature_c != null ? `${Math.round(g.temperature_c)}°C` : "—"}</div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rounded-2xl border border-border bg-card p-5">
              <div className="text-sm font-semibold mb-3">Peripherals</div>
              <div className="text-sm space-y-2">
                <div><span className="text-muted-foreground">USB devices:</span> {usbInv.count ?? 0}</div>
                <div><span className="text-muted-foreground">Printers:</span> {printers.count ?? 0}{printers.items?.length ? ` · ${printers.items.map((p) => p.name).slice(0, 3).join(", ")}` : ""}</div>
                <div><span className="text-muted-foreground">Monitors:</span> {monitors.count ?? 0}{monitors.items?.length ? ` · ${monitors.items.map((m) => m.friendly_name || m.name || m.raw || "").filter(Boolean).slice(0, 3).join(", ")}` : ""}</div>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* SOFTWARE */}
        <TabsContent value="software" className="mt-4">
          {(inv.installed_software && (Array.isArray(inv.installed_software) ? inv.installed_software.length : (inv.installed_software.items || []).length)) ? (
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <div className="px-5 py-3 border-b border-border flex items-center justify-between">
                <div className="text-sm font-semibold">Installed software · {Array.isArray(inv.installed_software) ? inv.installed_software.length : (inv.installed_software.items || []).length}</div>
                <div className="text-xs text-muted-foreground">Reported by the agent</div>
              </div>
              <div className="max-h-[520px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-background/60 border-b border-border sticky top-0"><tr className="text-left text-xs text-muted-foreground"><th className="px-4 py-3 font-medium">Name</th><th className="px-3 py-3 font-medium">Version</th><th className="px-3 py-3 font-medium">Publisher</th></tr></thead>
                  <tbody>
                    {(Array.isArray(inv.installed_software) ? inv.installed_software : (inv.installed_software.items || [])).slice(0, 500).map((s, i) => (
                      <tr key={i} className="border-t border-border"><td className="px-4 py-2 truncate max-w-[280px]">{s.name}</td><td className="px-3 py-2 font-mono text-xs text-muted-foreground">{s.version || "—"}</td><td className="px-3 py-2 text-muted-foreground truncate max-w-[240px]">{s.publisher || "—"}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : <EmptyState icon={Package} title="No software inventory yet" description="Software list is collected hourly. Trigger 'Refresh Inventory' from Maintenance to fetch it now." />}
        </TabsContent>

        {/* PROCESSES */}
        <TabsContent value="processes" className="mt-4">
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <div className="px-5 py-3 border-b border-border text-sm font-semibold">Top processes by CPU · {procs.count ?? 0} total</div>
              <div className="max-h-[520px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-background/60 border-b border-border sticky top-0"><tr className="text-left text-xs text-muted-foreground"><th className="px-4 py-2 font-medium">PID</th><th className="px-3 py-2 font-medium">Name</th><th className="px-3 py-2 font-medium">User</th><th className="px-3 py-2 font-medium tabular-nums">CPU %</th><th className="px-3 py-2 font-medium tabular-nums">Mem %</th></tr></thead>
                  <tbody>
                    {(procs.top || []).map((p, i) => (
                      <tr key={i} className="border-t border-border"><td className="px-4 py-1.5 font-mono text-xs">{p.pid}</td><td className="px-3 py-1.5 truncate max-w-[200px]">{p.name}</td><td className="px-3 py-1.5 text-muted-foreground truncate max-w-[120px]">{p.username || "—"}</td><td className="px-3 py-1.5 tabular-nums">{p.cpu_percent?.toFixed(1) ?? "—"}</td><td className="px-3 py-1.5 tabular-nums">{p.memory_percent?.toFixed(1) ?? "—"}</td></tr>
                    ))}
                    {(!procs.top || procs.top.length === 0) && <tr><td colSpan={5} className="px-4 py-6 text-center text-sm text-muted-foreground">No processes reported yet.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <div className="px-5 py-3 border-b border-border text-sm font-semibold">Services · {services.count ?? 0}</div>
              <div className="max-h-[520px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-background/60 border-b border-border sticky top-0"><tr className="text-left text-xs text-muted-foreground"><th className="px-4 py-2 font-medium">Name</th><th className="px-3 py-2 font-medium">Status</th><th className="px-3 py-2 font-medium">Description</th></tr></thead>
                  <tbody>
                    {(services.items || []).slice(0, 300).map((s, i) => (
                      <tr key={i} className="border-t border-border"><td className="px-4 py-1.5 font-mono text-xs truncate max-w-[220px]">{s.name}</td><td className="px-3 py-1.5"><StatBadge variant={s.active === "active" || s.status === "running" ? "healthy" : "offline"}>{s.active || s.status || "—"}</StatBadge></td><td className="px-3 py-1.5 text-muted-foreground truncate max-w-[240px]">{s.description || s.display_name || "—"}</td></tr>
                    ))}
                    {(!services.items || services.items.length === 0) && <tr><td colSpan={3} className="px-4 py-6 text-center text-sm text-muted-foreground">No services reported yet.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* NETWORK */}
        <TabsContent value="network" className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
            <MetricTile icon={Globe} label="Public IP" value={m.public_ip ? <span className="font-mono text-lg">{m.public_ip}</span> : null} testId="net-pub-ip" />
            <MetricTile icon={Server} label="Private IP" value={device.ip_address ? <span className="font-mono text-lg">{device.ip_address}</span> : null} testId="net-priv-ip" />
            <MetricTile icon={Radio} label="MAC" value={device.mac_address ? <span className="font-mono text-sm">{device.mac_address}</span> : null} testId="net-mac" />
            <MetricTile icon={TrendingDown} label="Download" value={m.net_down_kbps != null ? Math.round(m.net_down_kbps) : null} unit="kbps" testId="net-down" tone="info" />
            <MetricTile icon={TrendingUp} label="Upload" value={m.net_up_kbps != null ? Math.round(m.net_up_kbps) : null} unit="kbps" testId="net-up" tone="info" />
            <MetricTile icon={Activity} label="Latency" value={m.latency_ms != null ? m.latency_ms : null} unit="ms" testId="net-latency" tone={m.latency_ms > 100 ? "warning" : "success"} />
          </div>
          <div className="rounded-2xl border border-border bg-card overflow-hidden">
            <div className="px-5 py-3 border-b border-border text-sm font-semibold">Network adapters</div>
            {adapters.length === 0 ? <div className="p-6 text-sm text-muted-foreground">No adapter data yet.</div> : (
              <table className="w-full text-sm">
                <thead className="bg-background/60 border-b border-border"><tr className="text-left text-xs text-muted-foreground"><th className="px-4 py-2 font-medium">Name</th><th className="px-3 py-2 font-medium">IPv4</th><th className="px-3 py-2 font-medium">IPv6</th><th className="px-3 py-2 font-medium">MAC</th><th className="px-3 py-2 font-medium">State</th><th className="px-3 py-2 font-medium tabular-nums">Speed</th></tr></thead>
                <tbody>
                  {adapters.map((a, i) => (
                    <tr key={i} className="border-t border-border"><td className="px-4 py-2 font-mono truncate max-w-[180px]">{a.name}</td><td className="px-3 py-2 font-mono text-xs">{a.ipv4 || "—"}</td><td className="px-3 py-2 font-mono text-xs truncate max-w-[200px]">{a.ipv6 || "—"}</td><td className="px-3 py-2 font-mono text-xs">{a.mac || "—"}</td><td className="px-3 py-2"><StatBadge variant={a.is_up ? "healthy" : "offline"}>{a.is_up ? "up" : "down"}</StatBadge></td><td className="px-3 py-2 tabular-nums">{a.speed_mbps ? `${a.speed_mbps} Mbps` : "—"}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </TabsContent>

        {/* USERS */}
        <TabsContent value="users" className="mt-4">
          <div className="rounded-2xl border border-border bg-card p-5">
            <div className="text-sm font-semibold flex items-center gap-2 mb-3"><UsersIcon className="h-4 w-4 text-primary" /> Currently logged-in users</div>
            {users.length === 0 ? <div className="text-sm text-muted-foreground">No users reported yet.</div> : (
              <ul className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {users.map((u, i) => (
                  <li key={i} className="rounded-xl border border-border bg-foreground/[0.02] p-3 flex items-center gap-3">
                    <div className="h-9 w-9 rounded-full bg-gradient-to-br from-primary/40 to-cyan-500/40 flex items-center justify-center text-xs font-semibold">{(u || "?").charAt(0).toUpperCase()}</div>
                    <div className="min-w-0"><div className="font-medium truncate">{u}</div><div className="text-[11px] text-muted-foreground">Session active</div></div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </TabsContent>

        {/* EVENT LOGS */}
        <TabsContent value="events" className="mt-4">
          {events?.items?.length ? (
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <div className="px-5 py-3 border-b border-border text-sm font-semibold">Recent OS event log · {events.count ?? events.items.length}</div>
              <div className="max-h-[600px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-background/60 border-b border-border sticky top-0"><tr className="text-left text-xs text-muted-foreground"><th className="px-4 py-2 font-medium">Log</th><th className="px-3 py-2 font-medium">Level</th><th className="px-3 py-2 font-medium">Source</th><th className="px-3 py-2 font-medium">Time</th><th className="px-3 py-2 font-medium">Message</th></tr></thead>
                  <tbody>
                    {events.items.map((e, i) => (
                      <tr key={i} className="border-t border-border">
                        <td className="px-4 py-1.5">{e.log || "system"}</td>
                        <td className="px-3 py-1.5"><StatBadge variant={e.level === "error" ? "critical" : e.level === "warning" ? "warning" : "info"}>{e.level || "info"}</StatBadge></td>
                        <td className="px-3 py-1.5 truncate max-w-[180px]">{e.source || "—"}</td>
                        <td className="px-3 py-1.5 text-muted-foreground text-xs whitespace-nowrap">{e.time || (e.raw ? e.raw.split(" ")[0] : "—")}</td>
                        <td className="px-3 py-1.5 truncate max-w-[420px]">{e.message || e.raw || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : <EmptyState icon={ScrollText} title="No event logs yet" description="The agent samples OS event logs during its hourly inventory sweep." />}
        </TabsContent>

        {/* ALERTS */}
        <TabsContent value="alerts" className="mt-4">
          {alerts.length === 0 ? <EmptyState icon={BellRing} title="No alerts for this device" description="Alerts appear here when thresholds are crossed (CPU / RAM / temperature / disk)." /> : (
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-background/60 border-b border-border"><tr className="text-left text-xs text-muted-foreground"><th className="px-4 py-3 font-medium">Severity</th><th className="px-4 py-3 font-medium">Kind</th><th className="px-4 py-3 font-medium">Message</th><th className="px-4 py-3 font-medium">When</th><th className="px-4 py-3 font-medium">State</th></tr></thead>
                <tbody>
                  {alerts.map((a) => (
                    <tr key={a.id} className="border-t border-border"><td className="px-4 py-2"><StatBadge variant={severityColor(a.severity)}>{a.severity}</StatBadge></td><td className="px-4 py-2 text-muted-foreground">{a.kind}</td><td className="px-4 py-2">{a.message}</td><td className="px-4 py-2 text-muted-foreground">{formatRelative(a.ts)}</td><td className="px-4 py-2">{a.resolved_at ? <StatBadge variant="healthy">Resolved</StatBadge> : a.acknowledged_at ? <StatBadge variant="info">Ack'd</StatBadge> : <StatBadge variant="warning">Open</StatBadge>}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>

        {/* HEALTH & PREDICTION */}
        <TabsContent value="health" className="mt-4">
          <HealthAssessmentPanel
            deviceId={deviceId}
            liveOverride={liveHealth}
          />
        </TabsContent>

        {/* AI PREDICTION (Rule + Scikit-learn) */}
        <TabsContent value="ai-prediction" className="mt-4">
          <PredictionPanel deviceId={deviceId} />
        </TabsContent>

        {/* REMOTE MANAGEMENT (full command console) */}
        <TabsContent value="remote" className="mt-4">
          <RemoteManagementPanel deviceId={deviceId} currentUser={user} />
        </TabsContent>

        {/* MAINTENANCE */}
        <TabsContent value="maintenance" className="mt-4">
          <div className="space-y-4">
            {canTech && (
              <div className="rounded-2xl border border-border bg-card p-5">
                <div className="text-sm font-semibold">Remote actions</div>
                <div className="mt-1 text-xs text-muted-foreground">The agent picks up pending actions on its next check-in.</div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <ActionButton icon={RefreshCw} label="Refresh inventory" kind="refresh_inventory" deviceId={deviceId} onQueued={loadAll} />
                  <ActionButton icon={Trash2} label="Clear temp files" kind="clear_temp" deviceId={deviceId} onQueued={loadAll} />
                  <ActionButton icon={Lock} label="Lock computer" kind="lock" deviceId={deviceId} onQueued={loadAll} />
                  <ActionButton icon={RotateCcw} label="Restart" kind="restart" deviceId={deviceId} onQueued={loadAll} destructive />
                  <ActionButton icon={Power} label="Shutdown" kind="shutdown" deviceId={deviceId} onQueued={loadAll} destructive />
                </div>
              </div>
            )}
            <div className="rounded-2xl border border-border bg-card p-5">
              <div className="text-sm font-semibold mb-3 flex items-center gap-2"><History className="h-4 w-4 text-primary" /> Maintenance timeline</div>
              {timeline.length === 0 ? <div className="text-sm text-muted-foreground">No maintenance events yet.</div> : (
                <ol className="relative border-l border-border ml-3 space-y-4">
                  {timeline.map((e, i) => (
                    <li key={i} className="ml-4">
                      <div className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full bg-primary/60 border border-primary" />
                      <div className="flex items-center gap-2 mb-1"><StatBadge variant={severityColor(e.severity)}>{e.kind}</StatBadge><span className="text-[11px] text-muted-foreground">{formatRelative(e.ts)}</span></div>
                      <div className="text-sm font-medium">{e.title}</div>
                      <div className="text-xs text-muted-foreground">{e.subtitle}</div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        </TabsContent>

        {/* DIAGNOSTICS */}
        <TabsContent value="diagnostics" className="mt-4">
          <div className="rounded-2xl border border-border bg-card p-5">
            <AgentDiagnosticsPanel deviceId={deviceId} />
          </div>
        </TabsContent>

        {/* RECOMMENDATIONS */}
        <TabsContent value="recommendations" className="mt-4">
          <div className="rounded-2xl border border-border bg-card p-5">
            <div className="text-sm font-semibold mb-3 flex items-center gap-2"><Lightbulb className="h-4 w-4 text-amber-400" /> Live recommendations</div>
            <ul className="space-y-2">
              {recommendations.map((r, i) => (
                <li key={i} className="rounded-xl border border-border bg-foreground/[0.02] p-3 flex items-start gap-3">
                  <StatBadge variant={r.level === "critical" ? "critical" : r.level === "warning" ? "warning" : r.level === "success" ? "healthy" : "info"}>{r.level}</StatBadge>
                  <div><div className="text-sm font-medium">{r.title}</div><div className="text-xs text-muted-foreground mt-0.5">{r.body}</div></div>
                </li>
              ))}
            </ul>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
