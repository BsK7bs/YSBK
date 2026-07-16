import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { motion } from "framer-motion";
import {
  ScrollText, Filter, RefreshCw, X, ChevronDown, ChevronUp,
  RotateCcw, Copy, Check, Download, Loader2, Search,
} from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../contexts/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { StatBadge } from "../components/StatBadge";
import { hasRole, formatRelative } from "../lib/format";

const STATUS_TO_VARIANT = {
  pending: "info", in_progress: "warning", succeeded: "healthy",
  failed: "critical", cancelled: "offline", expired: "offline",
};

export default function CommandHistoryPage() {
  const { user } = useAuth();
  const canTech = hasRole(user, "technician");
  const [items, setItems] = useState([]);
  const [devices, setDevices] = useState({});
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: actions }, { data: dev }] = await Promise.all([
        api.get("/actions", { params: { limit: 200, ...(statusFilter ? { status: statusFilter } : {}) } }),
        api.get("/devices"),
      ]);
      setItems(actions || []);
      const dmap = {};
      const list = Array.isArray(dev) ? dev : (dev?.items || []);
      for (const d of list) dmap[d.id] = d;
      setDevices(dmap);
    } catch (e) {
      toast.error("Failed to load command history");
    } finally { setLoading(false); }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  const filtered = items.filter((a) => {
    if (!search) return true;
    const q = search.toLowerCase();
    const dev = devices[a.device_id] || {};
    return (
      a.kind?.toLowerCase().includes(q) ||
      a.created_by_email?.toLowerCase().includes(q) ||
      (dev.hostname || "").toLowerCase().includes(q) ||
      (dev.display_name || "").toLowerCase().includes(q) ||
      JSON.stringify(a.params || {}).toLowerCase().includes(q)
    );
  });

  const retry = async (id) => {
    try {
      await api.post(`/actions/${id}/retry`);
      toast.success("Retry queued");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Retry failed");
    }
  };

  const exportCsv = () => {
    const header = ["time", "device", "user", "command", "status", "exit_code", "error"].join(",");
    const rows = filtered.map((a) => {
      const dev = devices[a.device_id] || {};
      const cmd = a.params?.command || a.params?.script || a.params?.service_name || a.params?.package || a.kind;
      const exit = a.result?.returncode ?? a.result?.exit_code ?? "";
      const q = (v) => `"${String(v ?? "").replace(/"/g, '""').replace(/\n/g, " ")}"`;
      return [q(a.created_at), q(dev.hostname || dev.display_name || a.device_id), q(a.created_by_email), q(cmd), q(a.status), q(exit), q(a.error || "")].join(",");
    });
    const csv = [header, ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `command-history-${Date.now()}.csv`;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4" data-testid="command-history-page">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <div className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <ScrollText className="h-6 w-6 text-primary" /> Command History
          </div>
          <div className="text-sm text-muted-foreground">Every remote command executed across the fleet.</div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search kind, user, device..." className="pl-8 w-64" data-testid="history-search" />
          </div>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
            className="h-9 rounded-md border border-border bg-foreground/[0.03] px-3 text-sm">
            <option value="">All statuses</option>
            {["pending", "in_progress", "succeeded", "failed", "cancelled", "expired"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <Button variant="outline" onClick={load}><RefreshCw className="h-4 w-4" /></Button>
          <Button variant="outline" onClick={exportCsv}><Download className="h-4 w-4 mr-1" /> Export CSV</Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin" /></div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center text-sm text-muted-foreground">
          No commands match your filters.
        </div>
      ) : (
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-foreground/[0.03] text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="text-left p-3 font-medium">Time</th>
                <th className="text-left p-3 font-medium">Device</th>
                <th className="text-left p-3 font-medium">User</th>
                <th className="text-left p-3 font-medium">Command</th>
                <th className="text-left p-3 font-medium">Status</th>
                <th className="text-left p-3 font-medium">Exit</th>
                <th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((a) => {
                const dev = devices[a.device_id] || {};
                const preview = a.params?.command || a.params?.script || a.params?.service_name || a.params?.package || "—";
                const exit = a.result?.returncode ?? a.result?.exit_code;
                const isOpen = expanded === a.id;
                const isTerminal = ["succeeded", "failed", "cancelled", "expired"].includes(a.status);
                return (
                  <React.Fragment key={a.id}>
                    <tr className="border-t border-border hover:bg-foreground/[0.02]" data-testid={`history-row-${a.id}`}>
                      <td className="p-3 text-xs text-muted-foreground whitespace-nowrap">{formatRelative(a.created_at)}</td>
                      <td className="p-3 text-xs truncate max-w-[160px]" title={dev.hostname}>{dev.hostname || dev.display_name || a.device_id?.slice(0, 8)}</td>
                      <td className="p-3 text-xs truncate max-w-[180px]" title={a.created_by_email}>{a.created_by_email || "system"}</td>
                      <td className="p-3 text-xs"><span className="font-medium">{a.kind}</span> <span className="font-mono text-muted-foreground">{String(preview).slice(0, 40)}{String(preview).length > 40 ? "…" : ""}</span></td>
                      <td className="p-3"><StatBadge variant={STATUS_TO_VARIANT[a.status] || "info"}>{a.status}</StatBadge></td>
                      <td className="p-3 text-xs font-mono">{exit ?? "—"}</td>
                      <td className="p-3 flex items-center gap-1 justify-end">
                        {isTerminal && canTech && a.status !== "succeeded" && (
                          <Button size="sm" variant="outline" onClick={() => retry(a.id)} data-testid={`history-retry-${a.id}`}>
                            <RotateCcw className="h-3 w-3" />
                          </Button>
                        )}
                        <Button size="sm" variant="ghost" onClick={() => setExpanded(isOpen ? null : a.id)}>
                          {isOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                        </Button>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="border-t border-border/40 bg-black/20">
                        <td colSpan={7} className="p-3">
                          <ExpandedRow action={a} onDownload={() => downloadArtifact(a.id)} />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

async function downloadArtifact(id) {
  try {
    const { data } = await api.get(`/actions/${id}/artifact`);
    const blob = new Blob([Uint8Array.from(atob(data.content_b64), (c) => c.charCodeAt(0))], { type: data.content_type || "application/zip" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = data.filename || `${id}.zip`;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  } catch (e) {
    toast.error(e?.response?.data?.detail || "Artifact unavailable");
  }
}

function ExpandedRow({ action, onDownload }) {
  const [copied, setCopied] = useState(false);
  const result = action.result || {};
  const stdout = typeof result.stdout === "string" ? result.stdout : null;
  const stderr = typeof result.stderr === "string" ? result.stderr : null;
  const hasArtifact = ["download_logs", "collect_event_logs", "collect_diagnostic", "collect_crash_dumps"].includes(action.kind) && action.status === "succeeded";

  const copy = (t) => {
    navigator.clipboard.writeText(t);
    setCopied(true); setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="space-y-2 text-xs">
      <div className="flex flex-wrap gap-4">
        <div><span className="text-muted-foreground">Params:</span> <code className="font-mono">{JSON.stringify(action.params || {}, null, 0)}</code></div>
        {action.batch_id && <div><span className="text-muted-foreground">Batch:</span> <code className="font-mono">{action.batch_id.slice(0, 12)}…</code></div>}
        {action.parent_action_id && <div><span className="text-muted-foreground">Retry of:</span> <code className="font-mono">{action.parent_action_id.slice(0, 12)}…</code></div>}
        {hasArtifact && <Button size="sm" variant="outline" onClick={onDownload}><Download className="h-3 w-3 mr-1" /> Artifact</Button>}
      </div>
      {action.error && <div className="rounded-md border border-red-500/30 bg-red-500/10 text-red-200 p-2">{action.error}</div>}
      {stdout && (
        <div>
          <div className="flex items-center gap-2 text-[10px] uppercase text-muted-foreground mb-1">
            stdout
            <button onClick={() => copy(stdout)} className="ml-auto inline-flex items-center gap-1 hover:text-foreground">
              {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />} {copied ? "copied" : "copy"}
            </button>
          </div>
          <pre className="bg-black/40 border border-border rounded-md p-2 whitespace-pre-wrap max-h-64 overflow-auto font-mono">{stdout}</pre>
        </div>
      )}
      {stderr && (
        <div>
          <div className="text-[10px] uppercase text-muted-foreground mb-1">stderr</div>
          <pre className="bg-black/40 border border-red-500/30 rounded-md p-2 whitespace-pre-wrap max-h-40 overflow-auto font-mono text-red-200">{stderr}</pre>
        </div>
      )}
    </div>
  );
}
