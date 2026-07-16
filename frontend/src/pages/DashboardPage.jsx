import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  MonitorSmartphone,
  Activity,
  ShieldAlert,
  ShieldCheck,
  ArrowRight,
  Bell,
  Plus,
  Search,
  Filter,
  Cpu,
  MemoryStick,
  HardDrive,
  Thermometer,
  Wifi,
  Zap,
  X,
  Download,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  LineChart,
  Line,
} from "recharts";

import { KpiCard } from "../components/KpiCard";
import { TopAtRiskWidget } from "../components/TopAtRiskWidget";
import { EmptyState } from "../components/EmptyState";
import { StatBadge, RiskBadge, OnlineBadge } from "../components/StatBadge";
import { LiveIndicator } from "../components/LiveIndicator";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { api } from "../lib/api";
import { useDashboardSocket } from "../contexts/WebSocketContext";
import { useAuth } from "../contexts/AuthContext";
import { formatRelative, severityColor, hasRole } from "../lib/format";
import EnrollDeviceDialog from "../components/EnrollDeviceDialog";
import RegisterComputerDialog from "../components/RegisterComputerDialog";

const MAX_POINTS = 40;

// ---------------- Chart component --------------------
function FleetChart({ title, subtitle, series, dataKey, unit, color, valueFormatter, yDomain, testId }) {
  const displayValue = useMemo(() => {
    if (!series || series.length === 0) return null;
    return series[series.length - 1]?.[dataKey];
  }, [series, dataKey]);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.2, 0.8, 0.2, 1] }}
      className="rounded-2xl border border-border bg-card p-4 sm:p-5 shadow-[var(--shadow-1)] card-hover relative overflow-hidden"
      data-testid={testId}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-widest text-muted-foreground font-medium">{title}</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums" data-testid={`${testId}-value`}>
            {displayValue == null ? "—" : (valueFormatter ? valueFormatter(displayValue) : displayValue)}
            {displayValue != null && unit && <span className="ml-1 text-sm text-muted-foreground">{unit}</span>}
          </div>
          {subtitle && <div className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</div>}
        </div>
        <LiveIndicator label="Live" className="mt-1" />
      </div>
      <div className="mt-3 h-[140px] w-full">
        {series && series.length > 0 ? (
          <ResponsiveContainer>
            <AreaChart data={series} margin={{ top: 4, right: 6, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={`grad-${testId}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.45} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
              <XAxis dataKey="t" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} minTickGap={30} />
              <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} domain={yDomain || ["auto", "auto"]} width={30} tickFormatter={(v) => (v >= 1000 ? `${Math.round(v / 100) / 10}k` : v)} />
              <Tooltip
                contentStyle={{ background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 10, fontSize: 12 }}
                labelStyle={{ color: "hsl(var(--muted-foreground))", fontSize: 11 }}
                formatter={(v) => [valueFormatter ? valueFormatter(v) : v, title]}
              />
              <Area type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} fill={`url(#grad-${testId})`} isAnimationActive animationDuration={400} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full w-full flex items-center justify-center text-xs text-muted-foreground border border-dashed border-border rounded-xl">
            Waiting for telemetry…
          </div>
        )}
      </div>
    </motion.div>
  );
}

function AnimatedNumber({ value, testId }) {
  const prev = useRef(0);
  const [display, setDisplay] = useState(value ?? 0);
  useEffect(() => {
    const target = Number(value ?? 0);
    const start = prev.current;
    const duration = 500;
    const startTime = performance.now();
    let raf;
    const tick = (now) => {
      const t = Math.min(1, (now - startTime) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(Math.round(start + (target - start) * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
      else prev.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <span className="tabular-nums" data-testid={testId}>{display}</span>;
}

function Kpi({ label, value, icon: Icon, tone, hint, testId, onClick }) {
  const toneStyle = {
    default: "bg-primary/10 text-primary border-primary/25",
    success: "bg-emerald-500/10 text-emerald-300 border-emerald-500/25",
    warning: "bg-amber-500/10 text-amber-300 border-amber-500/25",
    critical: "bg-red-500/10 text-red-300 border-red-500/25",
    offline: "bg-slate-500/10 text-slate-300 border-slate-500/25",
  }[tone] || "bg-primary/10 text-primary border-primary/25";

  return (
    <motion.button
      layout
      whileHover={{ y: -2 }}
      whileTap={{ scale: 0.99 }}
      transition={{ type: "spring", stiffness: 300, damping: 22 }}
      onClick={onClick}
      className="text-left w-full rounded-2xl border border-border bg-card p-4 sm:p-5 shadow-[var(--shadow-1)] card-hover relative overflow-hidden"
      data-testid={testId}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">{label}</div>
        <div className={`h-9 w-9 rounded-xl border flex items-center justify-center ${toneStyle}`}>
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <div className="mt-2 text-3xl font-semibold tracking-tight" data-testid={`${testId}-value`}>
        <AnimatedNumber value={value ?? 0} testId={`${testId}-num`} />
      </div>
      {hint && <div className="mt-1 text-[11px] text-muted-foreground">{hint}</div>}
    </motion.button>
  );
}

// ---------------- Main dashboard --------------------
export default function DashboardPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { subscribe, status: wsStatus } = useDashboardSocket();

  const [summary, setSummary] = useState(null);
  const [devicesMap, setDevicesMap] = useState({}); // id -> device
  const [alerts, setAlerts] = useState([]);
  const [audit, setAudit] = useState([]);
  const [openEnroll, setOpenEnroll] = useState(false);
  const [openRegister, setOpenRegister] = useState(false);

  // Filters that scope the KPI/chart aggregation
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    const id = setTimeout(() => setDebouncedQ(q.trim().toLowerCase()), 250);
    return () => clearTimeout(id);
  }, [q]);

  // Fetch initial snapshot
  const loadSnapshot = useCallback(async () => {
    try {
      const [s, d, a] = await Promise.all([
        api.get("/devices/summary"),
        api.get("/devices?page=1&page_size=200"),
        api.get("/alerts?limit=15"),
      ]);
      setSummary(s.data);
      const items = d.data?.items || [];
      const map = {};
      items.forEach((it) => (map[it.id] = it));
      setDevicesMap(map);
      setAlerts(a.data || []);
    } catch {
      // handled by interceptor
    }
    if (hasRole(user, "admin")) {
      try {
        const au = await api.get("/audit?limit=10");
        setAudit(au.data || []);
      } catch {}
    }
  }, [user]);

  useEffect(() => {
    loadSnapshot();
  }, [loadSnapshot]);

  // Rolling series computed from WS + snapshot
  const [seriesCpu, setSeriesCpu] = useState([]);
  const [seriesRam, setSeriesRam] = useState([]);
  const [seriesDisk, setSeriesDisk] = useState([]);
  const [seriesTemp, setSeriesTemp] = useState([]);
  const [seriesNet, setSeriesNet] = useState([]);
  const [pulseAlerts, setPulseAlerts] = useState(false);

  const pushPoint = (setter, value, extra = {}) => {
    if (value == null || Number.isNaN(value)) return;
    setter((prev) => {
      const t = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      const next = [...prev, { t, value: Number(value.toFixed ? value.toFixed(1) : value), ...extra }];
      return next.slice(-MAX_POINTS);
    });
  };

  // Filter helper: returns true when device passes the current filters
  const matchesFilter = useCallback(
    (dev) => {
      if (!dev) return false;
      if (debouncedQ) {
        const hay = `${dev.hostname || ""} ${dev.display_name || ""} ${dev.ip_address || ""} ${dev.mac_address || ""} ${dev.os_name || ""} ${dev.cpu || ""} ${(dev.tags || []).join(" ")}`.toLowerCase();
        if (!hay.includes(debouncedQ)) return false;
      }
      if (statusFilter === "online" && !dev.is_online) return false;
      if (statusFilter === "offline" && dev.is_online) return false;
      if (statusFilter === "warning" && dev.risk_level !== "warning") return false;
      if (statusFilter === "critical" && dev.risk_level !== "critical") return false;
      if (statusFilter === "healthy" && dev.risk_level !== "healthy") return false;
      return true;
    },
    [debouncedQ, statusFilter],
  );

  // Recompute aggregates whenever devicesMap or filter changes
  const filteredDevices = useMemo(() => Object.values(devicesMap).filter(matchesFilter), [devicesMap, matchesFilter]);

  const filteredKpis = useMemo(() => {
    const arr = filteredDevices;
    const online = arr.filter((d) => d.is_online).length;
    const offline = arr.length - online;
    const warning = arr.filter((d) => d.risk_level === "warning").length;
    const critical = arr.filter((d) => d.risk_level === "critical").length;
    const healthy = arr.filter((d) => d.risk_level === "healthy").length;
    const scored = arr.filter((d) => typeof d.health_score === "number");
    const avg = scored.length ? Math.round(scored.reduce((s, d) => s + d.health_score, 0) / scored.length) : null;
    return { total: arr.length, online, offline, warning, critical, healthy, avg_health: avg };
  }, [filteredDevices]);

  // Live WS updates
  useEffect(() => {
    const unsub = subscribe((msg) => {
      if (msg.type === "telemetry") {
        // Update device latest_metrics
        setDevicesMap((prev) => {
          const cur = prev[msg.device_id];
          if (!cur) return prev;
          return {
            ...prev,
            [msg.device_id]: {
              ...cur,
              latest_metrics: { ...(cur.latest_metrics || {}), ...(msg.metrics || {}) },
              health_score: msg.health_score ?? cur.health_score,
              risk_level: msg.risk_level ?? cur.risk_level,
              last_seen: msg.ts,
              is_online: true,
            },
          };
        });
      } else if (msg.type === "device.online" || msg.type === "device.offline") {
        setDevicesMap((prev) => {
          const cur = prev[msg.device_id];
          if (!cur) return prev;
          return { ...prev, [msg.device_id]: { ...cur, is_online: msg.type === "device.online" } };
        });
      } else if (msg.type === "inventory") {
        // Refresh individual device data (fields may have changed)
        api.get(`/devices/${msg.device_id}`).then((r) => {
          setDevicesMap((prev) => ({ ...prev, [msg.device_id]: r.data }));
        }).catch(() => {});
      } else if (msg.type === "alerts") {
        setPulseAlerts(true);
        setTimeout(() => setPulseAlerts(false), 1500);
        api.get("/alerts?limit=15").then((r) => setAlerts(r.data || [])).catch(() => {});
      }
    });
    return unsub;
  }, [subscribe]);

  // Recompute chart series periodically from current filtered devices (1s tick)
  useEffect(() => {
    const compute = () => {
      const arr = filteredDevices.filter((d) => d.is_online);
      if (arr.length === 0) return;
      const avg = (fn) => {
        const vals = arr.map(fn).filter((v) => typeof v === "number" && !Number.isNaN(v));
        return vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : null;
      };
      const sum = (fn) => arr.map(fn).filter((v) => typeof v === "number").reduce((s, v) => s + v, 0);
      const cpu = avg((d) => d.latest_metrics?.cpu_percent);
      const ram = avg((d) => d.latest_metrics?.ram_percent);
      const disk = avg((d) => d.latest_metrics?.disk_percent);
      const temp = avg((d) => d.latest_metrics?.cpu_temp_c);
      const netUp = sum((d) => d.latest_metrics?.net_up_kbps);
      const netDown = sum((d) => d.latest_metrics?.net_down_kbps);

      if (cpu != null) pushPoint(setSeriesCpu, cpu);
      if (ram != null) pushPoint(setSeriesRam, ram);
      if (disk != null) pushPoint(setSeriesDisk, disk);
      if (temp != null) pushPoint(setSeriesTemp, temp);
      if ((netUp || 0) + (netDown || 0) > 0) pushPoint(setSeriesNet, netUp + netDown, { up: netUp, down: netDown });
    };
    // First sample immediately, then every 5s
    compute();
    const id = setInterval(compute, 5000);
    return () => clearInterval(id);
  }, [filteredDevices]);

  const isEmpty = summary && summary.total === 0;
  const canManage = hasRole(user, "technician");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-3">
            <div className="text-2xl font-semibold tracking-tight">Fleet Overview</div>
            <StatBadge variant={wsStatus === "connected" ? "online" : wsStatus === "connecting" ? "warning" : "offline"} pulse={wsStatus === "connected"}>
              {wsStatus === "connected" ? "Live" : wsStatus === "connecting" ? "Connecting" : "Offline"}
            </StatBadge>
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            Real-time health across your organization's devices
            {debouncedQ || statusFilter !== "all" ? (
              <span> · scoped to <span className="text-foreground font-medium">{filteredKpis.total}</span> matching device{filteredKpis.total === 1 ? "" : "s"}</span>
            ) : null}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {canManage && (
            <>
              <button
                onClick={() => setOpenRegister(true)}
                data-testid="dashboard-register-button"
                className="inline-flex items-center gap-2 h-10 px-4 rounded-xl border border-border bg-foreground/[0.03] hover:bg-foreground/[0.06] text-sm font-medium"
              >
                <Plus className="h-4 w-4" /> Register
              </button>
              <button
                onClick={() => setOpenEnroll(true)}
                data-testid="dashboard-enroll-button"
                className="inline-flex items-center gap-2 h-10 px-4 rounded-xl bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 shadow-[var(--shadow-1)]"
              >
                <Download className="h-4 w-4" /> Download Agent
              </button>
            </>
          )}
        </div>
      </div>

      {/* Filters */}
      <motion.div layout className="rounded-2xl border border-border bg-card p-3 sm:p-4 flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[240px] max-w-lg">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter by hostname, IP, MAC, OS, tag…"
            className="pl-9 pr-9"
            data-testid="dashboard-search-input"
          />
          {q && (
            <button
              onClick={() => setQ("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 h-6 w-6 rounded-md hover:bg-foreground/10 flex items-center justify-center"
              aria-label="Clear search"
            >
              <X className="h-3 w-3 text-muted-foreground" />
            </button>
          )}
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[160px]" data-testid="dashboard-filter-status">
            <Filter className="h-4 w-4 mr-1 text-muted-foreground" />
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="online">Online only</SelectItem>
            <SelectItem value="offline">Offline only</SelectItem>
            <SelectItem value="healthy">Healthy</SelectItem>
            <SelectItem value="warning">Warning</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
          </SelectContent>
        </Select>
        {(debouncedQ || statusFilter !== "all") && (
          <button
            onClick={() => { setQ(""); setStatusFilter("all"); }}
            className="text-xs text-muted-foreground hover:text-foreground px-2 py-1"
          >
            Clear filters
          </button>
        )}
      </motion.div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <Kpi label="Total Devices" value={filteredKpis.total} icon={MonitorSmartphone} tone="default" hint={`${filteredKpis.healthy} healthy · ${filteredKpis.total - filteredKpis.healthy - filteredKpis.warning - filteredKpis.critical} other`} testId="kpi-total" onClick={() => navigate("/app/devices")} />
        <Kpi label="Online" value={filteredKpis.online} icon={Activity} tone="success" hint={`${filteredKpis.online} reporting live`} testId="kpi-online" onClick={() => navigate("/app/devices?status=online")} />
        <Kpi label="Offline" value={filteredKpis.offline} icon={ShieldCheck} tone="offline" hint="No recent telemetry" testId="kpi-offline" onClick={() => navigate("/app/devices?status=offline")} />
        <Kpi label="Warning" value={filteredKpis.warning} icon={ShieldAlert} tone="warning" hint="Elevated resource usage" testId="kpi-warning" onClick={() => navigate("/app/devices?status=warning")} />
        <Kpi label="Critical" value={filteredKpis.critical} icon={Zap} tone="critical" hint="Immediate attention" testId="kpi-critical" onClick={() => navigate("/app/devices?status=critical")} />
      </div>

      {isEmpty ? (
        <EmptyState
          icon={MonitorSmartphone}
          title="No devices enrolled yet"
          description="Start monitoring your fleet by enrolling a computer with the desktop agent, or manually register machines to track their inventory."
          primaryLabel="Download Agent"
          primaryAction={canManage ? () => setOpenEnroll(true) : undefined}
          secondary={
            canManage ? (
              <button
                onClick={() => setOpenRegister(true)}
                className="inline-flex items-center gap-2 h-10 px-4 rounded-xl border border-border bg-foreground/[0.03] hover:bg-foreground/[0.06] text-sm font-medium"
              >
                <Plus className="h-4 w-4" /> Register manually
              </button>
            ) : null
          }
        />
      ) : (
        <>
          {/* Charts */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            <FleetChart title="CPU" subtitle="Fleet-wide average" series={seriesCpu} dataKey="value" unit="%" color="hsl(var(--primary))" valueFormatter={(v) => (v == null ? "—" : Math.round(v))} yDomain={[0, 100]} testId="chart-cpu" />
            <FleetChart title="RAM" subtitle="Fleet-wide average" series={seriesRam} dataKey="value" unit="%" color="hsl(var(--info))" valueFormatter={(v) => (v == null ? "—" : Math.round(v))} yDomain={[0, 100]} testId="chart-ram" />
            <FleetChart title="Disk" subtitle="Highest-percent partition (avg)" series={seriesDisk} dataKey="value" unit="%" color="hsl(var(--chart-3))" valueFormatter={(v) => (v == null ? "—" : Math.round(v))} yDomain={[0, 100]} testId="chart-disk" />
            <FleetChart title="CPU Temperature" subtitle="Fleet-wide average" series={seriesTemp} dataKey="value" unit="°C" color="hsl(var(--warning))" valueFormatter={(v) => (v == null ? "—" : Math.round(v))} yDomain={[0, 100]} testId="chart-temp" />
            <FleetChart title="Network" subtitle="Combined upload + download" series={seriesNet} dataKey="value" unit="kbps" color="hsl(var(--chart-2))" valueFormatter={(v) => (v == null ? "—" : Math.round(v).toLocaleString())} testId="chart-net" />
            <RecentAlertsPanel alerts={alerts} pulse={pulseAlerts} onNavigate={() => navigate("/app/alerts")} devicesMap={devicesMap} />
          </div>

          {/* AI Prediction — Top at-risk devices */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            <TopAtRiskWidget />
          </div>

          {/* At-risk & activity */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            <RiskyDevicesTable devices={filteredDevices} onOpen={(id) => navigate(`/app/devices/${id}`)} />
            {hasRole(user, "admin") && <ActivityFeed events={audit} />}
          </div>
        </>
      )}

      <EnrollDeviceDialog
        open={openEnroll}
        onOpenChange={setOpenEnroll}
        onEnrolled={() => { loadSnapshot(); toast.success("Pairing code created"); }}
      />
      <RegisterComputerDialog
        open={openRegister}
        onOpenChange={setOpenRegister}
        onRegistered={() => { loadSnapshot(); }}
      />
    </div>
  );
}

// -------------------- Panels --------------------
function RecentAlertsPanel({ alerts, pulse, onNavigate, devicesMap }) {
  return (
    <motion.div
      layout
      className="rounded-2xl border border-border bg-card p-4 sm:p-5 shadow-[var(--shadow-1)] relative overflow-hidden"
      animate={pulse ? { boxShadow: ["0 0 0 0 rgba(239,68,68,0)", "0 0 0 6px rgba(239,68,68,0.15)", "0 0 0 0 rgba(239,68,68,0)"] } : {}}
      transition={{ duration: 1.2 }}
    >
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-sm font-semibold flex items-center gap-2"><Bell className="h-4 w-4 text-amber-400" /> Recent alerts</div>
          <div className="text-[11px] text-muted-foreground">Last 15 events across the fleet</div>
        </div>
        <button onClick={onNavigate} className="text-xs text-primary hover:underline inline-flex items-center gap-1">
          View all <ArrowRight className="h-3 w-3" />
        </button>
      </div>
      {alerts.length === 0 ? (
        <div className="h-[140px] rounded-xl border border-dashed border-border flex items-center justify-center text-xs text-muted-foreground">
          No alerts yet
        </div>
      ) : (
        <ul className="space-y-2 max-h-[220px] overflow-auto pr-1">
          <AnimatePresence initial={false}>
            {alerts.slice(0, 6).map((a) => {
              const dev = devicesMap[a.device_id];
              return (
                <motion.li
                  key={a.id}
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 6 }}
                  transition={{ duration: 0.2 }}
                  className="rounded-xl border border-border bg-foreground/[0.02] p-3"
                >
                  <div className="flex items-center gap-2">
                    <StatBadge variant={severityColor(a.severity)}>{a.severity}</StatBadge>
                    <div className="text-xs text-muted-foreground ml-auto">{formatRelative(a.ts)}</div>
                  </div>
                  <div className="mt-1.5 text-sm font-medium truncate">{a.message}</div>
                  <div className="text-[11px] text-muted-foreground truncate">{dev ? (dev.display_name || dev.hostname) : a.kind}</div>
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ul>
      )}
    </motion.div>
  );
}

function RiskyDevicesTable({ devices, onOpen }) {
  const top = useMemo(() => {
    return [...devices]
      .filter((d) => typeof d.health_score === "number")
      .sort((a, b) => (a.health_score ?? 100) - (b.health_score ?? 100))
      .slice(0, 8);
  }, [devices]);

  return (
    <motion.div layout className="lg:col-span-8 rounded-2xl border border-border bg-card p-4 sm:p-5 shadow-[var(--shadow-1)]">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-sm font-semibold">Devices needing attention</div>
          <div className="text-[11px] text-muted-foreground">Lowest health scores first</div>
        </div>
      </div>
      {top.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-6 text-sm text-muted-foreground">
          Every online device is currently healthy. 🎉
        </div>
      ) : (
        <div className="overflow-x-auto -mx-4 sm:mx-0">
          <table className="w-full text-sm" data-testid="dashboard-risky-table">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="font-medium px-4 sm:px-3 py-2">Device</th>
                <th className="font-medium px-3 py-2">Status</th>
                <th className="font-medium px-3 py-2">Risk</th>
                <th className="font-medium px-3 py-2 tabular-nums">CPU</th>
                <th className="font-medium px-3 py-2 tabular-nums">RAM</th>
                <th className="font-medium px-3 py-2 tabular-nums">Disk</th>
                <th className="font-medium px-3 py-2 tabular-nums">Health</th>
                <th className="font-medium px-3 py-2">Last seen</th>
              </tr>
            </thead>
            <tbody>
              {top.map((d) => (
                <tr
                  key={d.id}
                  onClick={() => onOpen(d.id)}
                  className="cursor-pointer hover:bg-foreground/[0.03] border-t border-border transition-colors"
                  data-testid="risky-device-row"
                >
                  <td className="px-4 sm:px-3 py-2 font-medium truncate max-w-[240px]">{d.display_name || d.hostname}</td>
                  <td className="px-3 py-2"><OnlineBadge online={d.is_online} /></td>
                  <td className="px-3 py-2"><RiskBadge risk={d.is_online ? d.risk_level : "offline"} /></td>
                  <td className="px-3 py-2 tabular-nums">{d.latest_metrics?.cpu_percent != null ? `${d.latest_metrics.cpu_percent.toFixed(0)}%` : "—"}</td>
                  <td className="px-3 py-2 tabular-nums">{d.latest_metrics?.ram_percent != null ? `${d.latest_metrics.ram_percent.toFixed(0)}%` : "—"}</td>
                  <td className="px-3 py-2 tabular-nums">{d.latest_metrics?.disk_percent != null ? `${d.latest_metrics.disk_percent.toFixed(0)}%` : "—"}</td>
                  <td className="px-3 py-2 tabular-nums">{d.health_score ?? "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{formatRelative(d.last_seen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </motion.div>
  );
}

function ActivityFeed({ events }) {
  return (
    <motion.div layout className="lg:col-span-4 rounded-2xl border border-border bg-card p-4 sm:p-5 shadow-[var(--shadow-1)]">
      <div className="text-sm font-semibold mb-3">Recent activity</div>
      {events.length === 0 ? (
        <div className="text-sm text-muted-foreground">No activity yet.</div>
      ) : (
        <ul className="space-y-2">
          {events.slice(0, 8).map((e) => (
            <li key={e.id} className="rounded-lg px-2 py-1.5 hover:bg-foreground/[0.03]">
              <div className="text-xs font-medium truncate">{e.kind}</div>
              <div className="text-[11px] text-muted-foreground truncate">
                {e.actor_email || "system"} · {formatRelative(e.ts)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </motion.div>
  );
}
