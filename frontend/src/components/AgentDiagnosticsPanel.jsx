import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, Server, Wifi, WifiOff, AlertTriangle, CheckCircle2, XCircle, Clock, Cpu, Package, Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { extractError, formatRelative } from "../lib/format";
import { Button } from "./ui/button";

/**
 * Agent Diagnostics panel (Phase 7 § 7.9).
 *
 * Consumes ``/api/agents/{device_id}/diagnostics`` and presents the last
 * uploaded snapshot plus history. Refreshes every 15s while the tab is
 * mounted.
 */
export default function AgentDiagnosticsPanel({ deviceId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await api.get(`/agents/${deviceId}/diagnostics`);
      setData(r.data);
    } catch (e) {
      toast.error(extractError(e, "Failed to load diagnostics"));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [deviceId]);

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12" data-testid="diagnostics-loading">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  const latest = data?.latest;
  const dev = data?.device;
  const enrolled = Boolean(dev?.enrolled_at);

  return (
    <div className="space-y-4" data-testid="diagnostics-panel">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Agent Diagnostics</h3>
        <Button size="sm" variant="ghost" onClick={load} disabled={refreshing} data-testid="diagnostics-refresh">
          <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <StatusTile
          icon={ShieldCheck}
          label="Enrollment"
          value={enrolled ? "Verified" : "Missing"}
          state={enrolled ? "ok" : "bad"}
          subline={dev?.enrolled_at ? `Enrolled ${formatRelative(dev.enrolled_at)}` : "Device never paired"}
          testid="diag-enrollment"
        />
        <StatusTile
          icon={Server}
          label="Windows Service"
          value={latest?.service_status || "Unknown"}
          state={latest?.service_status === "RUNNING" ? "ok" : latest?.service_status ? "warn" : "unknown"}
          subline={latest ? `Snapshot ${formatRelative(latest.ts)}` : "Awaiting first upload"}
          testid="diag-service"
        />
        <StatusTile
          icon={latest?.ws_state === "connected" ? Wifi : WifiOff}
          label="WebSocket"
          value={latest?.ws_state || "Unknown"}
          state={latest?.ws_state === "connected" ? "ok" : latest?.ws_state === "connecting" ? "warn" : "bad"}
          subline={dev?.is_online ? `Online · last seen ${formatRelative(dev.last_seen)}` : "Not currently online"}
          testid="diag-ws"
        />
        <StatusTile
          icon={Clock}
          label="Last heartbeat"
          value={latest?.last_heartbeat ? formatRelative(latest.last_heartbeat) : "—"}
          state={latest?.last_heartbeat ? "ok" : "unknown"}
          subline={latest?.last_heartbeat ? latest.last_heartbeat : "No heartbeat recorded"}
          testid="diag-heartbeat"
        />
        <StatusTile
          icon={Cpu}
          label="Last telemetry"
          value={latest?.last_telemetry ? formatRelative(latest.last_telemetry) : "—"}
          state={latest?.last_telemetry ? "ok" : "unknown"}
          subline={latest?.last_telemetry || "No telemetry uploaded"}
          testid="diag-telemetry"
        />
        <StatusTile
          icon={Package}
          label="Version"
          value={latest?.agent_version || dev?.agent_version || "—"}
          state={latest?.agent_version ? "ok" : "unknown"}
          subline={`Installer ${latest?.installer_version || dev?.installer_version || "—"}`}
          testid="diag-version"
        />
      </div>

      {latest?.last_error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3 flex gap-2" data-testid="diag-last-error">
          <AlertTriangle className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-xs font-semibold text-red-500">Last error</div>
            <div className="text-xs text-red-500/90 mt-1 font-mono break-all">{latest.last_error}</div>
          </div>
        </div>
      )}

      <div className="rounded-lg border border-border overflow-hidden">
        <div className="px-4 py-2 bg-foreground/5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Device identity</div>
        <dl className="grid sm:grid-cols-2 gap-x-6 gap-y-2 p-4 text-xs">
          <DL k="Hostname" v={latest?.hostname || dev?.hostname} />
          <DL k="OS" v={`${latest?.os_name || dev?.os_name || "—"} ${dev?.os_version || ""}`.trim()} />
          <DL k="IP address" v={latest?.ip_address || "—"} mono />
          <DL k="MAC address" v={latest?.mac_address || "—"} mono />
          <DL k="Device ID" v={dev?.id} mono />
          <DL k="Enrolled via token" v={dev?.enrolled_via_token_id || "—"} mono />
        </dl>
      </div>

      {data?.history && data.history.length > 0 && (
        <details className="rounded-lg border border-border">
          <summary className="cursor-pointer select-none px-4 py-2 text-xs font-semibold uppercase tracking-wide bg-foreground/5 text-muted-foreground">
            Recent diagnostic history ({data.history.length})
          </summary>
          <div className="max-h-64 overflow-auto">
            <table className="w-full text-[11px]">
              <thead className="sticky top-0 bg-background">
                <tr className="text-left text-muted-foreground">
                  <th className="px-3 py-2 font-medium">When</th>
                  <th className="px-3 py-2 font-medium">Service</th>
                  <th className="px-3 py-2 font-medium">WS</th>
                  <th className="px-3 py-2 font-medium">Error</th>
                </tr>
              </thead>
              <tbody>
                {data.history.map((h) => (
                  <tr key={h.ts + (h._hid || "")} className="border-t border-border/50">
                    <td className="px-3 py-1.5 font-mono">{formatRelative(h.ts)}</td>
                    <td className="px-3 py-1.5">{h.service_status || "—"}</td>
                    <td className="px-3 py-1.5">{h.ws_state || "—"}</td>
                    <td className="px-3 py-1.5 text-red-500/80 max-w-[240px] truncate" title={h.last_error || ""}>{h.last_error || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}

function StatusTile({ icon: Icon, label, value, state, subline, testid }) {
  const colour = state === "ok" ? "text-emerald-500 border-emerald-500/30 bg-emerald-500/5"
    : state === "warn" ? "text-amber-500 border-amber-500/30 bg-amber-500/5"
    : state === "bad" ? "text-red-500 border-red-500/30 bg-red-500/5"
    : "text-muted-foreground border-border bg-foreground/5";
  return (
    <div className={`rounded-lg border p-3 ${colour}`} data-testid={testid}>
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide font-semibold opacity-90">
        <Icon className="h-3.5 w-3.5" /> {label}
      </div>
      <div className="mt-1 text-sm font-semibold">{value || "—"}</div>
      <div className="text-[11px] opacity-70 mt-0.5">{subline}</div>
    </div>
  );
}

function DL({ k, v, mono }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="text-muted-foreground min-w-[120px]">{k}</dt>
      <dd className={mono ? "font-mono break-all" : ""}>{v || "—"}</dd>
    </div>
  );
}
