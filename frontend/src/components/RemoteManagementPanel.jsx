import React, { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Power, RefreshCw, Moon, Lock, Terminal, ScrollText, Zap, Trash2,
  Download, PlaySquare, Package, PackageMinus, ShieldAlert, Loader2,
  ChevronDown, ChevronUp, X, Copy, Check, FileArchive, ServerCog, Bug,
  FileText, Stethoscope, HardDriveDownload, RotateCw,
} from "lucide-react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "./ui/dialog";
import { StatBadge } from "./StatBadge";
import { toast } from "sonner";

/**
 * A catalogue-driven renderer for the Remote Management panel. Each
 * ``ACTION`` entry describes:
 *
 *   * ``kind``: matches the backend ``ActionKind`` literal
 *   * ``label`` / ``description`` / ``icon``: presentation
 *   * ``tone``: visual accent — "default" | "warning" | "critical" | "info"
 *   * ``group``: which section this action belongs to
 *   * ``params``: array of {name, label, type, placeholder, required, options?}
 *     used to auto-generate the form
 *   * ``adminOnly``: mirror of backend flag so we can hint to unprivileged users
 *   * ``requiresConfirm``: whether we show a "Type CONFIRM to proceed" gate
 */
const ACTIONS = [
  // -- Power --
  { kind: "restart", group: "Power",    label: "Restart PC",    description: "Reboot the machine in 5 seconds.",           icon: RefreshCw, tone: "warning",  adminOnly: true, requiresConfirm: true, params: [] },
  { kind: "shutdown", group: "Power",   label: "Shutdown PC",   description: "Power off the machine in 5 seconds.",        icon: Power,     tone: "critical", adminOnly: true, requiresConfirm: true, params: [] },
  { kind: "sleep", group: "Power",      label: "Sleep",         description: "Put the machine into suspend/sleep mode.",   icon: Moon,      tone: "info",     adminOnly: true, requiresConfirm: true, params: [] },
  { kind: "lock", group: "Power",       label: "Lock",          description: "Lock the active user session.",              icon: Lock,      tone: "info",     adminOnly: true, requiresConfirm: true, params: [] },

  // -- Execution --
  { kind: "exec_cmd", group: "Execute", label: "Run CMD command", description: "Execute a single cmd.exe command and stream stdout/stderr back.", icon: Terminal, tone: "warning", adminOnly: true, requiresConfirm: true,
    params: [{ name: "command", label: "Command", type: "text", placeholder: "ipconfig /all", required: true }] },
  { kind: "exec_powershell", group: "Execute", label: "Run PowerShell", description: "Execute a single PowerShell command (non-interactive).", icon: Terminal, tone: "warning", adminOnly: true, requiresConfirm: true,
    params: [{ name: "command", label: "Command", type: "text", placeholder: "Get-Service | Where-Object { $_.Status -eq 'Running' } | Select-Object -First 5", required: true }] },
  { kind: "run_script", group: "Execute", label: "Run Script",  description: "Execute a multi-line script in Python / Bash / PowerShell / CMD.", icon: PlaySquare, tone: "warning", adminOnly: true, requiresConfirm: true,
    params: [
      { name: "script", label: "Script body", type: "textarea", required: true, placeholder: "Write-Host 'hello from remote'" },
      { name: "interpreter", label: "Interpreter", type: "select", options: ["auto","powershell","cmd","bash","python"], defaultValue: "auto" },
    ] },

  // -- Processes & services --
  { kind: "kill_process", group: "Processes", label: "Kill Process", description: "Terminate a process by PID or by name.", icon: Zap, tone: "warning", adminOnly: true, requiresConfirm: true,
    params: [
      { name: "pid", label: "PID (optional)", type: "number", placeholder: "1234" },
      { name: "name", label: "Process name (optional)", type: "text", placeholder: "notepad.exe" },
    ] },
  { kind: "restart_service", group: "Processes", label: "Restart Service", description: "Stop and start a Windows/systemd service.", icon: ServerCog, tone: "warning", adminOnly: true, requiresConfirm: true,
    params: [{ name: "service_name", label: "Service name", type: "text", placeholder: "wuauserv", required: true }] },

  // -- Software --
  { kind: "install_software", group: "Software", label: "Install Software", description: "Install a package via winget / choco / apt / URL.", icon: Package, tone: "warning", adminOnly: true, requiresConfirm: true,
    params: [
      { name: "package", label: "Package ID / name", type: "text", placeholder: "Microsoft.VisualStudioCode", required: true },
      { name: "source", label: "Source", type: "select", options: ["winget","choco","apt","url"], defaultValue: "winget" },
      { name: "url", label: "Installer URL (only if source=url)", type: "text", placeholder: "https://…/setup.exe" },
    ] },
  { kind: "uninstall_software", group: "Software", label: "Uninstall Software", description: "Remove a package via winget / choco / apt.", icon: PackageMinus, tone: "warning", adminOnly: true, requiresConfirm: true,
    params: [{ name: "package", label: "Package ID / name", type: "text", placeholder: "Microsoft.VisualStudioCode", required: true }] },
  { kind: "run_windows_update", group: "Software", label: "Run Windows Update", description: "Trigger a scan → download → install cycle via usoclient.", icon: RefreshCw, tone: "warning", adminOnly: true, requiresConfirm: true, params: [] },

  // -- Maintenance --
  { kind: "clear_temp", group: "Maintenance", label: "Clear Temp", description: "Delete files in the OS temp directory.", icon: Trash2, tone: "warning", adminOnly: true, requiresConfirm: true, params: [] },
  { kind: "download_logs", group: "Maintenance", label: "Download Logs", description: "Zip the agent log directory and upload it back to the platform.", icon: FileArchive, tone: "info", adminOnly: false, requiresConfirm: false, params: [] },
  { kind: "refresh_inventory", group: "Maintenance", label: "Refresh Inventory", description: "Force a full-inventory push (software, USB, printers, monitors, SMART).", icon: ScrollText, tone: "default", adminOnly: false, requiresConfirm: false, params: [] },
  { kind: "restart_agent", group: "Maintenance", label: "Restart Monitoring Agent", description: "Restart the Digital Twin agent service without touching the OS.", icon: RotateCw, tone: "info", adminOnly: true, requiresConfirm: true, params: [] },

  // -- Remote File Collection --
  { kind: "collect_event_logs", group: "Files", label: "Collect Event Logs", description: "Collect Windows Event Log channels and upload as a zip.", icon: FileText, tone: "info", adminOnly: false, requiresConfirm: false,
    params: [
      { name: "channels", label: "Channels (comma-separated)", type: "text", placeholder: "System, Application, Security", defaultValue: "System,Application" },
      { name: "max_events", label: "Max events per channel", type: "number", placeholder: "500", defaultValue: 500 },
    ] },
  { kind: "collect_diagnostic", group: "Files", label: "Diagnostic Report", description: "Systeminfo, ipconfig, tasklist, drivers, netstat, disk health — zipped.", icon: Stethoscope, tone: "info", adminOnly: false, requiresConfirm: false, params: [] },
  { kind: "collect_crash_dumps", group: "Files", label: "Collect Crash Dumps", description: "Recent Windows minidumps and WER crash reports (max 5MB).", icon: HardDriveDownload, tone: "info", adminOnly: false, requiresConfirm: false, params: [] },
];

const GROUPS = ["Power", "Execute", "Processes", "Software", "Maintenance", "Files"];
const TONE_STYLES = {
  default:  "border-border hover:border-primary/60 hover:bg-primary/5",
  info:     "border-cyan-500/25 hover:border-cyan-500/60 hover:bg-cyan-500/5",
  warning:  "border-amber-500/25 hover:border-amber-500/60 hover:bg-amber-500/5",
  critical: "border-red-500/30 hover:border-red-500/60 hover:bg-red-500/5",
};
const ICON_TONE = {
  default: "text-primary bg-primary/10",
  info: "text-cyan-300 bg-cyan-500/10",
  warning: "text-amber-300 bg-amber-500/10",
  critical: "text-red-300 bg-red-500/10",
};
const STATUS_TO_VARIANT = {
  pending: "info",
  in_progress: "warning",
  succeeded: "healthy",
  failed: "critical",
  cancelled: "offline",
  expired: "offline",
};

function fmtRel(iso) {
  if (!iso) return "";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return new Date(iso).toLocaleString();
}


function ActionRunDialog({ open, onClose, action, deviceId, canAdmin, onEnqueued }) {
  const [params, setParams] = useState({});
  const [confirmText, setConfirmText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [validationErr, setValidationErr] = useState(null);

  useEffect(() => {
    if (!action) return;
    const initial = {};
    for (const p of action.params || []) if (p.defaultValue !== undefined) initial[p.name] = p.defaultValue;
    setParams(initial);
    setConfirmText("");
    setValidationErr(null);
  }, [action]);

  if (!action) return null;

  const needConfirm = action.requiresConfirm;
  const gateOk = !needConfirm || confirmText.trim().toUpperCase() === "CONFIRM";
  const missingRequired = (action.params || []).some((p) => p.required && !String(params[p.name] || "").trim());
  const canSubmit = gateOk && !missingRequired && !submitting && (!action.adminOnly || canAdmin);

  const submit = async () => {
    setSubmitting(true);
    setValidationErr(null);
    try {
      const preparedParams = { ...params };
      // Normalise comma-separated channels string -> array for collect_event_logs
      if (action.kind === "collect_event_logs" && typeof preparedParams.channels === "string") {
        preparedParams.channels = preparedParams.channels
          .split(",").map((s) => s.trim()).filter(Boolean);
      }
      const body = { kind: action.kind, params: preparedParams, confirm: needConfirm };
      const { data } = await api.post(`/actions/devices/${deviceId}`, body);
      toast.success(`${action.label} queued`);
      onEnqueued?.(data);
      onClose();
    } catch (e) {
      setValidationErr(e?.response?.data?.detail || e.message || "Failed to queue action");
    } finally {
      setSubmitting(false);
    }
  };

  const Icon = action.icon || PlaySquare;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg" data-testid={`action-dialog-${action.kind}`}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span className={`rounded-lg p-1.5 ${ICON_TONE[action.tone] || ICON_TONE.default}`}><Icon className="h-4 w-4" /></span>
            {action.label}
          </DialogTitle>
        </DialogHeader>
        <div className="text-sm text-muted-foreground">{action.description}</div>

        {action.adminOnly && !canAdmin && (
          <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200 flex items-start gap-2">
            <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5" />
            You need the <b>admin</b> role or higher to run this action.
          </div>
        )}

        {(action.params || []).length > 0 && (
          <div className="mt-4 space-y-3">
            {action.params.map((p) => (
              <div key={p.name}>
                <label className="text-xs uppercase tracking-wider text-muted-foreground mb-1 block">
                  {p.label}{p.required && <span className="text-red-400"> *</span>}
                </label>
                {p.type === "textarea" ? (
                  <Textarea
                    value={params[p.name] || ""}
                    onChange={(e) => setParams({ ...params, [p.name]: e.target.value })}
                    placeholder={p.placeholder}
                    rows={6}
                    className="font-mono text-xs"
                    data-testid={`action-param-${p.name}`}
                  />
                ) : p.type === "select" ? (
                  <select
                    value={params[p.name] || p.defaultValue || ""}
                    onChange={(e) => setParams({ ...params, [p.name]: e.target.value })}
                    className="w-full h-9 rounded-md border border-border bg-foreground/[0.03] px-3 text-sm"
                    data-testid={`action-param-${p.name}`}
                  >
                    {p.options.map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <Input
                    type={p.type === "number" ? "number" : "text"}
                    value={params[p.name] || ""}
                    onChange={(e) => setParams({ ...params, [p.name]: p.type === "number" ? Number(e.target.value) : e.target.value })}
                    placeholder={p.placeholder}
                    data-testid={`action-param-${p.name}`}
                  />
                )}
              </div>
            ))}
          </div>
        )}

        {needConfirm && (
          <div className="mt-4">
            <label className="text-xs uppercase tracking-wider text-muted-foreground mb-1 block">
              Type <span className="font-mono text-foreground">CONFIRM</span> to proceed
            </label>
            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="CONFIRM"
              className={gateOk ? "border-emerald-500/40" : ""}
              data-testid="action-confirm-input"
            />
          </div>
        )}

        {validationErr && (
          <div className="mt-3 text-xs text-red-300 rounded-lg border border-red-500/30 bg-red-500/10 p-2" data-testid="action-error">
            {validationErr}
          </div>
        )}

        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            onClick={submit}
            disabled={!canSubmit}
            className={action.tone === "critical" ? "bg-red-500 hover:bg-red-600 text-white"
                     : action.tone === "warning" ? "bg-amber-500 hover:bg-amber-600 text-black"
                     : undefined}
            data-testid="action-submit"
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : null}
            Run {action.label}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function ResultRow({ item, onCancel, onDownloadArtifact }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const kind = ACTIONS.find((a) => a.kind === item.kind) || { label: item.kind, icon: Bug, tone: "default" };
  const Icon = kind.icon;
  const isTerminal = ["succeeded", "failed", "cancelled", "expired"].includes(item.status);
  const result = item.result || {};
  const stdout = typeof result.stdout === "string" ? result.stdout : null;
  const stderr = typeof result.stderr === "string" ? result.stderr : null;

  const copyStdout = () => {
    if (!stdout) return;
    navigator.clipboard.writeText(stdout);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="rounded-xl border border-border bg-foreground/[0.02]"
      data-testid="action-history-row"
    >
      <div className="flex items-center gap-3 p-3">
        <span className={`rounded-lg p-1.5 shrink-0 ${ICON_TONE[kind.tone] || ICON_TONE.default}`}>
          <Icon className="h-4 w-4" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">
            {kind.label}
            {item.params?.command && <span className="ml-2 font-mono text-[11px] text-muted-foreground">{item.params.command.slice(0, 40)}{item.params.command.length > 40 ? "…" : ""}</span>}
            {item.params?.service_name && <span className="ml-2 font-mono text-[11px] text-muted-foreground">{item.params.service_name}</span>}
            {item.params?.package && <span className="ml-2 font-mono text-[11px] text-muted-foreground">{item.params.package}</span>}
          </div>
          <div className="text-[11px] text-muted-foreground">
            by {item.created_by_email || "?"} · {fmtRel(item.created_at)}
            {item.finished_at && ` · ran in ${Math.round((new Date(item.finished_at) - new Date(item.started_at || item.created_at)) / 100) / 10}s`}
          </div>
        </div>
        <StatBadge variant={STATUS_TO_VARIANT[item.status] || "info"} data-testid={`action-status-${item.id}`}>{item.status}</StatBadge>
        {!isTerminal && (
          <Button variant="outline" size="sm" onClick={() => onCancel(item.id)} data-testid={`action-cancel-${item.id}`}>
            <X className="h-3.5 w-3.5 mr-1" /> Cancel
          </Button>
        )}
        {["download_logs", "collect_event_logs", "collect_diagnostic", "collect_crash_dumps"].includes(item.kind) && item.status === "succeeded" && (
          <Button variant="outline" size="sm" onClick={() => onDownloadArtifact(item.id)} data-testid={`action-artifact-${item.id}`}>
            <Download className="h-3.5 w-3.5 mr-1" /> Download
          </Button>
        )}
        <button onClick={() => setExpanded((v) => !v)} className="text-muted-foreground hover:text-foreground" data-testid={`action-expand-${item.id}`}>
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      {expanded && (
        <div className="border-t border-border px-3 pb-3 pt-2 space-y-2">
          {item.error && (
            <div className="text-xs rounded-md border border-red-500/30 bg-red-500/10 text-red-200 p-2">{item.error}</div>
          )}
          {stdout && (
            <div>
              <div className="flex items-center gap-2 text-[11px] uppercase text-muted-foreground mb-1">
                stdout
                <button onClick={copyStdout} className="ml-auto text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
                  {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />} {copied ? "copied" : "copy"}
                </button>
              </div>
              <pre className="text-[11px] bg-black/40 border border-border rounded-md p-2 whitespace-pre-wrap max-h-56 overflow-auto font-mono" data-testid={`action-stdout-${item.id}`}>{stdout}</pre>
            </div>
          )}
          {stderr && (
            <div>
              <div className="text-[11px] uppercase text-muted-foreground mb-1">stderr</div>
              <pre className="text-[11px] bg-black/40 border border-red-500/30 rounded-md p-2 whitespace-pre-wrap max-h-40 overflow-auto font-mono text-red-200">{stderr}</pre>
            </div>
          )}
          {!stdout && !stderr && (
            <pre className="text-[11px] bg-black/30 border border-border rounded-md p-2 whitespace-pre-wrap max-h-40 overflow-auto font-mono">
              {JSON.stringify(item.result || {}, null, 2)}
            </pre>
          )}
        </div>
      )}
    </motion.div>
  );
}


export function RemoteManagementPanel({ deviceId, currentUser }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openAction, setOpenAction] = useState(null);
  const canAdmin = ["admin", "owner"].includes(currentUser?.role);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/actions`, { params: { device_id: deviceId, limit: 40 } });
      setHistory(Array.isArray(data) ? data : []);
    } finally {
      setLoading(false);
    }
  }, [deviceId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const t = setInterval(load, 5000); // poll while the panel is open
    return () => clearInterval(t);
  }, [load]);

  const grouped = useMemo(() => {
    const map = {};
    for (const a of ACTIONS) (map[a.group] = map[a.group] || []).push(a);
    return map;
  }, []);

  const cancel = async (id) => {
    try {
      await api.post(`/actions/${id}/cancel`);
      toast.success("Cancel requested");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to cancel");
    }
  };

  const downloadArtifact = async (id) => {
    try {
      const { data } = await api.get(`/actions/${id}/artifact`);
      // data.content_b64 → build a data URL and click it.
      const blob = new Blob([Uint8Array.from(atob(data.content_b64), (c) => c.charCodeAt(0))],
                            { type: data.content_type || "application/zip" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = data.filename || `${id}.zip`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Artifact unavailable");
    }
  };

  return (
    <div className="space-y-6" data-testid="remote-management-panel">
      {!canAdmin && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200 flex items-center gap-2">
          <ShieldAlert className="h-4 w-4" />
          You have the <b>{currentUser?.role || "viewer"}</b> role. Only <b>Download Logs</b> and <b>Refresh Inventory</b> are available. Contact your admin to run destructive actions.
        </div>
      )}

      {GROUPS.map((g) => (
        <div key={g}>
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">{g}</div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {(grouped[g] || []).map((a) => {
              const Icon = a.icon;
              const disabled = a.adminOnly && !canAdmin;
              return (
                <button
                  key={a.kind}
                  onClick={() => !disabled && setOpenAction(a)}
                  disabled={disabled}
                  data-testid={`action-tile-${a.kind}`}
                  className={`text-left rounded-xl border ${TONE_STYLES[a.tone]} bg-card p-3.5 transition-colors group ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`rounded-lg p-2 ${ICON_TONE[a.tone] || ICON_TONE.default}`}><Icon className="h-4 w-4" /></span>
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate">{a.label}</div>
                      <div className="text-[11px] text-muted-foreground truncate">{a.description}</div>
                    </div>
                    {a.adminOnly && (
                      <span className="ml-auto text-[10px] uppercase tracking-wider text-muted-foreground border border-border/60 rounded-full px-1.5 py-0.5">admin</span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      ))}

      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Recent commands</div>
          {loading && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
        </div>
        {history.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border p-6 text-sm text-muted-foreground text-center">
            No commands have been sent to this device yet.
          </div>
        ) : (
          <div className="space-y-2" data-testid="action-history">
            <AnimatePresence initial={false}>
              {history.map((it) => (
                <ResultRow key={it.id} item={it} onCancel={cancel} onDownloadArtifact={downloadArtifact} />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>

      <ActionRunDialog
        open={!!openAction}
        onClose={() => setOpenAction(null)}
        action={openAction}
        deviceId={deviceId}
        canAdmin={canAdmin}
        onEnqueued={() => load()}
      />
    </div>
  );
}

export default RemoteManagementPanel;
