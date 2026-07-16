import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, Bell, BellOff, Check, ChevronRight, Loader2, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useDashboardSocket } from "../contexts/WebSocketContext";
import { alertStatusLabel, extractError, formatRelative, hasRole, severityColor, severityLabel } from "../lib/format";
import { StatBadge } from "./StatBadge";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { useAuth } from "../contexts/AuthContext";

const SEV_ORDER = { critical: 4, high: 3, medium: 2, low: 1, info: 0 };

export function NotificationCenter() {
  const { user } = useAuth();
  const { subscribe } = useDashboardSocket();
  const navigate = useNavigate();
  const [summary, setSummary] = useState({ total_active: 0, unacknowledged: 0, by_severity: {} });
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const seenIds = useRef(new Set());

  const canAct = hasRole(user, "technician");

  const loadSummary = useCallback(async () => {
    try {
      const r = await api.get("/alerts/summary");
      setSummary(r.data || { total_active: 0, unacknowledged: 0, by_severity: {} });
    } catch { /* silent */ }
  }, []);

  const loadAlerts = useCallback(async () => {
    try {
      setLoading(true);
      const r = await api.get("/alerts?unresolved_only=true&limit=25&range=7d");
      const list = r.data || [];
      list.forEach((a) => seenIds.current.add(a.id));
      setAlerts(list);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSummary(); }, [loadSummary]);
  useEffect(() => { if (open) loadAlerts(); }, [open, loadAlerts]);

  // Real-time updates from WebSocket.
  useEffect(() => {
    return subscribe((msg) => {
      if (!msg || !msg.type) return;
      if (msg.type === "alert.opened" || msg.type === "alert.updated") {
        const a = msg.alert;
        if (!a) return;
        // Toast on new critical/high (only for first occurrence).
        if ((a.severity === "critical" || a.severity === "high") && !seenIds.current.has(a.id)) {
          seenIds.current.add(a.id);
          const label = severityLabel(a.severity);
          const deviceName = (a.context || {}).device_name || "device";
          toast[a.severity === "critical" ? "error" : "warning"](
            `${label}: ${a.title}`,
            {
              description: `${deviceName} — ${a.current_value ?? ""}${a.unit ? ` ${a.unit}` : ""}`.trim(),
              action: {
                label: "View",
                onClick: () => navigate(`/app/alerts?highlight=${a.id}`),
              },
            }
          );
        }
        loadSummary();
        if (open) loadAlerts();
      } else if (
        msg.type === "alert.acknowledged" ||
        msg.type === "alert.resolved" ||
        msg.type === "alert.closed" ||
        msg.type === "alert.awaiting_ack"
      ) {
        loadSummary();
        if (open) loadAlerts();
      }
    });
  }, [subscribe, open, loadSummary, loadAlerts, navigate]);

  const total = summary.total_active || 0;
  const critical = summary.by_severity?.critical || 0;
  const high = summary.by_severity?.high || 0;
  const badgeTone = critical > 0 ? "bg-red-500 text-white" : high > 0 ? "bg-orange-500 text-white" : total > 0 ? "bg-amber-500 text-white" : "bg-slate-500/40 text-foreground";

  const sortedAlerts = useMemo(
    () => [...(alerts || [])].sort(
      (a, b) => (SEV_ORDER[b.severity] || 0) - (SEV_ORDER[a.severity] || 0) ||
                new Date(b.last_seen_at || 0) - new Date(a.last_seen_at || 0)
    ),
    [alerts]
  );

  const doQuickAck = async (id) => {
    try {
      await api.post(`/alerts/${id}/acknowledge`, { note: "Ack from Notification Center" });
      toast.success("Acknowledged");
      loadSummary();
      loadAlerts();
    } catch (e) {
      toast.error(extractError(e, "Failed to acknowledge"));
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          data-testid="notification-center-bell"
          aria-label="Notifications"
          className="h-9 w-9 rounded-lg hover:bg-foreground/5 flex items-center justify-center relative"
        >
          {total > 0 ? <Bell className="h-4 w-4" /> : <BellOff className="h-4 w-4 text-muted-foreground" />}
          {total > 0 && (
            <span
              data-testid="notification-center-badge"
              className={`absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-semibold flex items-center justify-center ${badgeTone} ring-2 ring-background`}
            >
              {total > 99 ? "99+" : total}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={8}
        className="w-[380px] p-0 overflow-hidden"
        data-testid="notification-center-panel"
      >
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold">Notifications</div>
            <div className="text-[11px] text-muted-foreground">
              {total} active
              {critical ? <> · <span className="text-red-400 font-medium">{critical} critical</span></> : null}
              {high ? <> · <span className="text-orange-400 font-medium">{high} high</span></> : null}
            </div>
          </div>
          <Link
            to="/app/alerts"
            onClick={() => setOpen(false)}
            className="text-[11px] text-primary hover:underline inline-flex items-center gap-1"
            data-testid="notification-center-view-all"
          >
            View all <ChevronRight className="h-3 w-3" />
          </Link>
        </div>
        <div className="max-h-[420px] overflow-y-auto">
          {loading ? (
            <div className="p-6 flex items-center gap-2 text-sm text-muted-foreground justify-center">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : sortedAlerts.length === 0 ? (
            <div className="p-6 text-center text-sm text-muted-foreground">
              <ShieldAlert className="h-6 w-6 mx-auto mb-2 opacity-40" />
              You're all caught up.<br />No active alerts.
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {sortedAlerts.map((a) => (
                <li key={a.id} className="px-4 py-3 hover:bg-foreground/[0.03]" data-testid={`notification-item-${a.id}`}>
                  <div className="flex items-start gap-3">
                    <span className={`mt-1 h-2 w-2 rounded-full shrink-0 ${
                      a.severity === "critical" ? "bg-red-500" :
                      a.severity === "high" ? "bg-orange-500" :
                      a.severity === "medium" ? "bg-amber-500" :
                      a.severity === "low" ? "bg-cyan-500" : "bg-slate-500"
                    }`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <StatBadge variant={severityColor(a.severity)}>{severityLabel(a.severity)}</StatBadge>
                        <span className="text-[11px] text-muted-foreground">{alertStatusLabel(a.status)}</span>
                        {a.occurrence_count > 1 && (
                          <span className="text-[10px] text-muted-foreground bg-foreground/[0.05] px-1.5 py-0.5 rounded">
                            ×{a.occurrence_count}
                          </span>
                        )}
                      </div>
                      <div className="mt-1 text-sm font-medium truncate">{a.title}</div>
                      <div className="text-[11px] text-muted-foreground truncate">
                        {(a.context || {}).device_name || a.device_id} · {a.current_value ?? ""}{a.unit ? ` ${a.unit}` : ""}
                      </div>
                      <div className="mt-1 text-[10px] text-muted-foreground">{formatRelative(a.last_seen_at)}</div>
                    </div>
                    {canAct && a.status !== "acknowledged" && a.status !== "closed" && (
                      <button
                        onClick={() => doQuickAck(a.id)}
                        data-testid={`notification-quick-ack-${a.id}`}
                        className="shrink-0 h-7 px-2 rounded-md border border-border text-[11px] hover:bg-foreground/5 inline-flex items-center gap-1"
                        title="Acknowledge"
                      >
                        <Check className="h-3 w-3" /> Ack
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="border-t border-border px-4 py-2 flex items-center justify-between text-[11px] text-muted-foreground">
          <span>Real-time via WebSocket</span>
          <Link to="/app/settings/notifications" onClick={() => setOpen(false)} className="hover:text-foreground" data-testid="notification-center-settings-link">
            Notification settings
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );
}
