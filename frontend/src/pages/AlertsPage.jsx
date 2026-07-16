import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertTriangle, BellRing, Check, CheckCheck, ChevronRight, Clock,
  Filter, HardDrive, Info, Loader2, RefreshCw, Search, Shield,
  ShieldAlert, X,
} from "lucide-react";
import { api } from "../lib/api";
import { EmptyState } from "../components/EmptyState";
import { StatBadge } from "../components/StatBadge";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "../components/ui/sheet";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import {
  alertStatusColor, alertStatusLabel, extractError, formatRelative, hasRole, severityColor, severityLabel,
} from "../lib/format";
import { useAuth } from "../contexts/AuthContext";
import { useDashboardSocket } from "../contexts/WebSocketContext";
import { cn } from "../lib/utils";

const LANES = [
  { key: "critical", title: "Critical", icon: ShieldAlert, ring: "ring-red-500/30", accent: "text-red-300" },
  { key: "high",     title: "High",     icon: AlertTriangle, ring: "ring-orange-500/30", accent: "text-orange-300" },
  { key: "medium",   title: "Medium",   icon: Clock, ring: "ring-amber-500/30", accent: "text-amber-300" },
  { key: "low",      title: "Low",      icon: Info, ring: "ring-cyan-500/30", accent: "text-cyan-300" },
];

const RANGES = [
  { key: "1h", label: "Last hour" },
  { key: "24h", label: "Last 24 h" },
  { key: "7d", label: "Last 7 d" },
  { key: "30d", label: "Last 30 d" },
  { key: "all", label: "All time" },
];

function AlertCard({ alert, onOpen, onQuickAck, canAct, highlighted }) {
  const isAcked = alert.status === "acknowledged" || alert.status === "closed";
  const isCleared = alert.status === "resolved_awaiting_ack";
  return (
    <div
      className={cn(
        "rounded-xl border p-3 bg-foreground/[0.02] hover:bg-foreground/[0.05] transition-colors cursor-pointer",
        highlighted ? "border-primary/60 ring-2 ring-primary/40" : "border-border",
      )}
      onClick={onOpen}
      data-testid={`alert-card-${alert.id}`}
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <StatBadge variant={alertStatusColor(alert.status)}>{alertStatusLabel(alert.status)}</StatBadge>
            {alert.occurrence_count > 1 && (
              <span className="text-[10px] text-muted-foreground bg-foreground/[0.05] px-1.5 py-0.5 rounded">
                ×{alert.occurrence_count}
              </span>
            )}
            {isCleared && <span className="text-[10px] text-amber-300">Condition cleared</span>}
          </div>
          <div className="mt-1 text-sm font-medium truncate">{alert.title}</div>
          <div className="text-[11px] text-muted-foreground truncate">
            {(alert.context || {}).device_name || alert.device_id}
            {alert.current_value !== null && alert.current_value !== undefined
              ? <> · <span className="font-mono text-foreground/90">{String(alert.current_value)}{alert.unit ? ` ${alert.unit}` : ""}</span></>
              : null}
            {alert.threshold != null ? <> · thr {alert.threshold}{alert.unit || ""}</> : null}
          </div>
          <div className="mt-1 text-[10px] text-muted-foreground">{formatRelative(alert.last_seen_at)}</div>
        </div>
        {canAct && !isAcked && (
          <button
            onClick={(e) => { e.stopPropagation(); onQuickAck(alert.id); }}
            data-testid={`alert-quick-ack-${alert.id}`}
            className="shrink-0 h-7 w-7 rounded-md border border-border hover:bg-foreground/5 flex items-center justify-center"
            title="Acknowledge"
          >
            <Check className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  );
}

function TimelineEvent({ event }) {
  const KIND_LABEL = {
    created: "Created",
    updated: "Updated",
    escalated: "Escalated",
    de_escalated: "De-escalated",
    condition_cleared: "Condition cleared",
    acknowledged: "Acknowledged",
    note: "Note",
    resolved: "Resolved",
    closed: "Closed",
  };
  const KIND_COLOR = {
    created: "text-cyan-300",
    escalated: "text-red-300",
    de_escalated: "text-emerald-300",
    condition_cleared: "text-amber-300",
    acknowledged: "text-primary",
    resolved: "text-emerald-300",
    closed: "text-emerald-300",
    note: "text-muted-foreground",
  };
  return (
    <li className="flex gap-3 text-xs" data-testid="alert-event">
      <div className="mt-1 h-2 w-2 rounded-full bg-primary/70 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={cn("font-medium", KIND_COLOR[event.kind])}>{KIND_LABEL[event.kind] || event.kind}</span>
          <span className="text-muted-foreground text-[10px]">{formatRelative(event.ts)}</span>
          {event.actor_email && <span className="text-muted-foreground text-[10px]">by {event.actor_email}</span>}
        </div>
        {event.message && <div className="text-muted-foreground mt-0.5">{event.message}</div>}
        {(event.from_severity || event.to_severity) && (
          <div className="text-[10px] mt-0.5">
            {event.from_severity && <span className="text-muted-foreground">from </span>}
            {event.from_severity && <span className="font-mono">{event.from_severity}</span>}
            {event.to_severity && <span className="text-muted-foreground"> → </span>}
            {event.to_severity && <span className="font-mono">{event.to_severity}</span>}
          </div>
        )}
      </div>
    </li>
  );
}

function AlertDetailsDrawer({ alertId, onClose, refresh, canAct }) {
  const [alert, setAlert] = useState(null);
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!alertId) return;
    setLoading(true);
    api.get(`/alerts/${alertId}`).then((r) => setAlert(r.data)).finally(() => setLoading(false));
  }, [alertId]);

  const run = async (fn, successMsg) => {
    setBusy(true);
    try {
      await fn();
      toast.success(successMsg);
      const r = await api.get(`/alerts/${alertId}`);
      setAlert(r.data);
      refresh();
    } catch (e) {
      toast.error(extractError(e, "Action failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={!!alertId} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="w-full sm:max-w-xl overflow-y-auto" data-testid="alert-details-drawer">
        <SheetHeader className="mb-4">
          <SheetTitle>Alert details</SheetTitle>
        </SheetHeader>
        {loading || !alert ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </div>
        ) : (
          <div className="space-y-5">
            <div className="flex items-center gap-2 flex-wrap">
              <StatBadge variant={severityColor(alert.severity)}>{severityLabel(alert.severity)}</StatBadge>
              <StatBadge variant={alertStatusColor(alert.status)}>{alertStatusLabel(alert.status)}</StatBadge>
              <span className="text-[11px] text-muted-foreground">rule: <span className="font-mono">{alert.rule_key}</span></span>
              {alert.occurrence_count > 1 && (
                <span className="text-[11px] text-muted-foreground bg-foreground/[0.05] px-1.5 py-0.5 rounded">
                  {alert.occurrence_count} occurrences
                </span>
              )}
            </div>
            <div>
              <div className="text-lg font-semibold">{alert.title}</div>
              {alert.recommendation && (
                <div className="mt-1 text-sm text-muted-foreground">
                  <span className="font-medium text-foreground/90">Recommended:</span> {alert.recommendation}
                </div>
              )}
            </div>

            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-xs">
              <div className="flex gap-2"><dt className="text-muted-foreground min-w-[130px]">Device</dt><dd>
                {alert.device_id ? <Link className="hover:underline" to={`/app/devices/${alert.device_id}`}>{(alert.context || {}).device_name || alert.device_id}</Link> : "—"}
              </dd></div>
              <div className="flex gap-2"><dt className="text-muted-foreground min-w-[130px]">Category</dt><dd className="capitalize">{alert.category || "—"}</dd></div>
              <div className="flex gap-2"><dt className="text-muted-foreground min-w-[130px]">Current value</dt><dd className="font-mono">{alert.current_value != null ? `${alert.current_value}${alert.unit ? ` ${alert.unit}` : ""}` : "—"}</dd></div>
              <div className="flex gap-2"><dt className="text-muted-foreground min-w-[130px]">Threshold</dt><dd className="font-mono">{alert.threshold != null ? `${alert.threshold}${alert.unit ? ` ${alert.unit}` : ""}` : "—"}</dd></div>
              <div className="flex gap-2"><dt className="text-muted-foreground min-w-[130px]">First detected</dt><dd>{formatRelative(alert.first_detected_at)}</dd></div>
              <div className="flex gap-2"><dt className="text-muted-foreground min-w-[130px]">Last seen</dt><dd>{formatRelative(alert.last_seen_at)}</dd></div>
              {alert.condition_cleared_at && (
                <div className="flex gap-2"><dt className="text-muted-foreground min-w-[130px]">Condition cleared</dt><dd>{formatRelative(alert.condition_cleared_at)}</dd></div>
              )}
              {alert.acknowledged_at && (
                <div className="flex gap-2"><dt className="text-muted-foreground min-w-[130px]">Acknowledged</dt><dd>{formatRelative(alert.acknowledged_at)} by {alert.acknowledged_by_email || "—"}</dd></div>
              )}
              {alert.closed_at && (
                <div className="flex gap-2"><dt className="text-muted-foreground min-w-[130px]">Closed</dt><dd>{formatRelative(alert.closed_at)} ({alert.resolution_method})</dd></div>
              )}
            </dl>

            {alert.context && Object.keys(alert.context).length > 0 && (
              <div className="rounded-xl border border-border bg-foreground/[0.02] p-3">
                <div className="text-[11px] uppercase tracking-widest text-muted-foreground mb-2">Context</div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  {Object.entries(alert.context).map(([k, v]) => (
                    <div key={k} className="flex gap-2">
                      <span className="text-muted-foreground capitalize min-w-[110px]">{k.replace(/_/g, " ")}</span>
                      <span className="font-mono break-all">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div>
              <div className="text-[11px] uppercase tracking-widest text-muted-foreground mb-2">Timeline</div>
              <ul className="space-y-2 border-l border-border pl-3">
                {(alert.events || []).slice().reverse().map((e, i) => <TimelineEvent key={i} event={e} />)}
              </ul>
            </div>

            {canAct && alert.status !== "closed" && (
              <div className="rounded-xl border border-border bg-foreground/[0.02] p-3 space-y-3">
                <div className="text-sm font-semibold">Take action</div>
                <Textarea
                  data-testid="alert-note-input"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Add a note (optional)"
                  className="min-h-[70px] text-sm"
                />
                <div className="flex flex-wrap gap-2">
                  {alert.status !== "acknowledged" && (
                    <Button
                      variant="secondary"
                      disabled={busy}
                      onClick={() => run(() => api.post(`/alerts/${alert.id}/acknowledge`, { note }), "Acknowledged")}
                      data-testid="alert-action-acknowledge"
                    >
                      <Check className="h-4 w-4 mr-1" /> Acknowledge
                    </Button>
                  )}
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() => run(() => api.post(`/alerts/${alert.id}/resolve`, { note }), "Resolved")}
                    data-testid="alert-action-resolve"
                  >
                    <CheckCheck className="h-4 w-4 mr-1" /> Resolve & close
                  </Button>
                  {note.trim() && (
                    <Button
                      variant="ghost"
                      disabled={busy}
                      onClick={() => run(() => api.post(`/alerts/${alert.id}/note`, { note }), "Note added")}
                      data-testid="alert-action-note"
                    >
                      Add note only
                    </Button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

export default function AlertsPage() {
  const { user } = useAuth();
  const { subscribe } = useDashboardSocket();
  const location = useLocation();
  const navigate = useNavigate();
  const canAct = hasRole(user, "technician");

  const [alerts, setAlerts] = useState(null);
  const [summary, setSummary] = useState(null);
  const [severity, setSeverity] = useState("all");
  const [status, setStatus] = useState("active");
  const [rangeKey, setRangeKey] = useState("7d");
  const [q, setQ] = useState("");
  const [detailsId, setDetailsId] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const highlightId = useMemo(() => new URLSearchParams(location.search).get("highlight"), [location.search]);
  useEffect(() => { if (highlightId) setDetailsId(highlightId); }, [highlightId]);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const q1 = new URLSearchParams();
      q1.set("range", rangeKey);
      q1.set("limit", "500");
      if (severity !== "all") q1.set("severity", severity);
      if (status === "active") q1.set("unresolved_only", "true");
      else if (status !== "all") q1.set("status", status);
      const [a, s] = await Promise.all([api.get(`/alerts?${q1.toString()}`), api.get("/alerts/summary")]);
      setAlerts(a.data || []);
      setSummary(s.data || null);
    } finally { setRefreshing(false); }
  }, [severity, status, rangeKey]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    return subscribe((msg) => {
      if (!msg) return;
      if (["alert.opened", "alert.updated", "alert.acknowledged", "alert.resolved", "alert.closed", "alert.awaiting_ack"].includes(msg.type)) {
        load();
      }
    });
  }, [subscribe, load]);

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase();
    return (alerts || []).filter((a) => {
      if (!query) return true;
      const hay = `${a.title || ""} ${(a.context || {}).device_name || ""} ${a.rule_key || ""} ${a.current_value || ""}`.toLowerCase();
      return hay.includes(query);
    });
  }, [alerts, q]);

  const grouped = useMemo(() => {
    const g = { critical: [], high: [], medium: [], low: [], info: [] };
    for (const a of filtered) {
      (g[a.severity] || (g.info)).push(a);
    }
    return g;
  }, [filtered]);

  const doQuickAck = async (id) => {
    try { await api.post(`/alerts/${id}/acknowledge`, {}); toast.success("Acknowledged"); load(); }
    catch (e) { toast.error(extractError(e, "Failed to acknowledge")); }
  };

  return (
    <div className="space-y-6" data-testid="alerts-page">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-2xl font-semibold tracking-tight">Alerts</div>
          <div className="mt-1 text-sm text-muted-foreground">
            Enterprise alert lifecycle: dwell-based detection, dedup, escalation, and full timeline.
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <Search className="h-3.5 w-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search alerts…"
              className="h-10 w-52 pl-8"
              data-testid="alerts-search"
            />
          </div>
          <Select value={severity} onValueChange={setSeverity}>
            <SelectTrigger className="h-10 w-[150px]" data-testid="alerts-severity-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All severities</SelectItem>
              <SelectItem value="critical">Critical</SelectItem>
              <SelectItem value="high">High</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="low">Low</SelectItem>
              <SelectItem value="info">Info</SelectItem>
            </SelectContent>
          </Select>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="h-10 w-[160px]" data-testid="alerts-status-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="open">Open</SelectItem>
              <SelectItem value="resolved_awaiting_ack">Awaiting ack</SelectItem>
              <SelectItem value="acknowledged">Acknowledged</SelectItem>
              <SelectItem value="closed">Closed</SelectItem>
            </SelectContent>
          </Select>
          <Select value={rangeKey} onValueChange={setRangeKey}>
            <SelectTrigger className="h-10 w-[140px]" data-testid="alerts-range-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              {RANGES.map((r) => <SelectItem key={r.key} value={r.key}>{r.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <button onClick={load} className="h-10 w-10 rounded-lg border border-border hover:bg-foreground/5 flex items-center justify-center" data-testid="alerts-refresh" title="Refresh">
            {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="rounded-2xl border border-border bg-card p-4" data-testid="alerts-kpi-total">
            <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Active</div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">{summary.total_active}</div>
            <div className="text-[11px] text-muted-foreground">{summary.unacknowledged} unacknowledged</div>
          </div>
          {LANES.map((l) => (
            <div key={l.key} className={cn("rounded-2xl border border-border bg-card p-4 ring-1 ring-inset", l.ring)} data-testid={`alerts-kpi-${l.key}`}>
              <div className={cn("text-[11px] uppercase tracking-widest font-medium", l.accent)}>{l.title}</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums">{summary.by_severity?.[l.key] || 0}</div>
              <div className="text-[11px] text-muted-foreground">active</div>
            </div>
          ))}
        </div>
      )}

      {alerts === null ? (
        <div className="h-40 rounded-2xl border border-border bg-card animate-pulse" />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={BellRing}
          title="No alerts match your filters"
          description="Try widening the time range or clearing the severity/status filter. Alerts show up in real time as the engine detects sustained conditions."
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-4 gap-4">
          {LANES.map((lane) => {
            const items = grouped[lane.key] || [];
            const Icon = lane.icon;
            return (
              <div key={lane.key} className={cn("rounded-2xl border border-border bg-card p-3 ring-1 ring-inset", lane.ring)} data-testid={`alerts-lane-${lane.key}`}>
                <div className="flex items-center gap-2 px-1 pb-3">
                  <Icon className={cn("h-4 w-4", lane.accent)} />
                  <div className="text-sm font-semibold">{lane.title}</div>
                  <div className="ml-auto text-[11px] text-muted-foreground">{items.length}</div>
                </div>
                <div className="space-y-2 max-h-[70vh] overflow-y-auto pr-1">
                  {items.length === 0 ? (
                    <div className="text-center text-[11px] text-muted-foreground py-6">No {lane.title.toLowerCase()} alerts</div>
                  ) : items.map((a) => (
                    <AlertCard
                      key={a.id}
                      alert={a}
                      canAct={canAct}
                      onOpen={() => setDetailsId(a.id)}
                      onQuickAck={doQuickAck}
                      highlighted={a.id === highlightId}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Info lane (small; appears below when there are items) */}
      {grouped.info && grouped.info.length > 0 && (
        <div className="rounded-2xl border border-border bg-card p-3" data-testid="alerts-lane-info">
          <div className="flex items-center gap-2 px-1 pb-3">
            <Info className="h-4 w-4 text-slate-300" />
            <div className="text-sm font-semibold">Info</div>
            <div className="ml-auto text-[11px] text-muted-foreground">{grouped.info.length}</div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {grouped.info.map((a) => (
              <AlertCard key={a.id} alert={a} canAct={canAct}
                         onOpen={() => setDetailsId(a.id)} onQuickAck={doQuickAck}
                         highlighted={a.id === highlightId} />
            ))}
          </div>
        </div>
      )}

      <AlertDetailsDrawer alertId={detailsId} onClose={() => { setDetailsId(null); if (highlightId) navigate("/app/alerts", { replace: true }); }} refresh={load} canAct={canAct} />
    </div>
  );
}
