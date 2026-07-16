import React, { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import {
  Power, RefreshCw, Moon, Lock, Trash2, Zap, PlaySquare,
  ShieldAlert, Loader2, X, RotateCcw, CheckCircle2, XCircle,
  Clock, ChevronRight, Package,
} from "lucide-react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "./ui/dialog";
import { StatBadge } from "./StatBadge";

const BULK_ACTIONS = [
  { kind: "restart", label: "Restart PC", icon: RefreshCw, tone: "warning", requiresConfirm: true, params: [] },
  { kind: "shutdown", label: "Shutdown PC", icon: Power, tone: "critical", requiresConfirm: true, params: [] },
  { kind: "lock", label: "Lock", icon: Lock, tone: "info", requiresConfirm: true, params: [] },
  { kind: "clear_temp", label: "Clear Temp Files", icon: Trash2, tone: "warning", requiresConfirm: true, params: [] },
  { kind: "refresh_inventory", label: "Refresh Inventory", icon: RotateCcw, tone: "default", requiresConfirm: false, params: [] },
  { kind: "run_windows_update", label: "Windows Update", icon: Package, tone: "warning", requiresConfirm: true, params: [] },
  { kind: "restart_agent", label: "Restart Monitoring Agent", icon: Zap, tone: "info", requiresConfirm: true, params: [] },
  {
    kind: "run_script", label: "Run Approved Script", icon: PlaySquare, tone: "warning", requiresConfirm: true,
    params: [
      { name: "script", label: "Script", type: "textarea", required: true, placeholder: "Write-Host 'hello fleet'" },
      { name: "interpreter", label: "Interpreter", type: "select", options: ["auto", "powershell", "cmd", "bash", "python"], defaultValue: "auto" },
    ],
  },
];

const STATUS_TO_VARIANT = {
  pending: "info", in_progress: "warning", succeeded: "healthy",
  failed: "critical", cancelled: "offline", expired: "offline",
};

const STATUS_ICON = {
  pending: Clock, in_progress: Loader2, succeeded: CheckCircle2,
  failed: XCircle, cancelled: XCircle, expired: XCircle,
};

export function BulkActionsDialog({ open, onOpenChange, selectedDevices, canAdmin, onDone }) {
  const [step, setStep] = useState("choose"); // choose | configure | running | summary
  const [action, setAction] = useState(null);
  const [params, setParams] = useState({});
  const [confirmText, setConfirmText] = useState("");
  const [error, setError] = useState(null);
  const [batchId, setBatchId] = useState(null);
  const [batch, setBatch] = useState(null);
  const [poll, setPoll] = useState(0);

  useEffect(() => {
    if (!open) {
      setStep("choose"); setAction(null); setParams({}); setConfirmText(""); setError(null);
      setBatchId(null); setBatch(null); setPoll(0);
    }
  }, [open]);

  // Poll batch progress
  useEffect(() => {
    if (!batchId || step !== "running") return;
    let cancelled = false;
    const tick = async () => {
      try {
        const { data } = await api.get(`/actions/batches/${batchId}`);
        if (cancelled) return;
        setBatch(data);
        const c = data.status_counts || {};
        // If nothing left pending/in_progress, move to summary
        if ((c.pending || 0) + (c.in_progress || 0) === 0 && (c.total || 0) > 0) {
          setStep("summary");
        }
      } catch {}
    };
    tick();
    const id = setInterval(tick, 2000);
    return () => { cancelled = true; clearInterval(id); };
  }, [batchId, step, poll]);

  const chooseAction = (a) => {
    if (a.kind !== "refresh_inventory" && !canAdmin) {
      setError("You need the admin role to run this action.");
      return;
    }
    setAction(a);
    setParams(Object.fromEntries((a.params || []).filter((p) => p.defaultValue).map((p) => [p.name, p.defaultValue])));
    setStep("configure");
  };

  const canSubmit = useMemo(() => {
    if (!action) return false;
    if (action.requiresConfirm && confirmText.trim().toUpperCase() !== "CONFIRM") return false;
    return !(action.params || []).some((p) => p.required && !String(params[p.name] || "").trim());
  }, [action, params, confirmText]);

  const submit = async () => {
    if (!action) return;
    setError(null);
    try {
      const { data } = await api.post("/actions/bulk", {
        kind: action.kind,
        params,
        device_ids: selectedDevices.map((d) => d.id),
        confirm: action.requiresConfirm,
        label: `bulk ${action.label} — ${selectedDevices.length} devices`,
      });
      setBatchId(data.batch_id);
      setBatch({ status_counts: { total: data.total, pending: data.total }, actions: data.actions, ...data });
      setStep("running");
      if (data.skipped?.length) {
        toast.warning(`${data.skipped.length} device(s) skipped`);
      }
      onDone?.();
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "Failed to enqueue bulk action");
    }
  };

  const retry = async (actionId) => {
    try {
      await api.post(`/actions/${actionId}/retry`);
      setPoll((n) => n + 1);
      toast.success("Retry queued");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Retry failed");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl" data-testid="bulk-actions-dialog">
        <DialogHeader>
          <DialogTitle>
            {step === "choose" && `Bulk Actions — ${selectedDevices.length} devices selected`}
            {step === "configure" && `Configure: ${action?.label}`}
            {step === "running" && "Running fleet action…"}
            {step === "summary" && "Fleet action complete"}
          </DialogTitle>
          {step === "choose" && (
            <DialogDescription>Pick an action to execute on every selected device.</DialogDescription>
          )}
        </DialogHeader>

        {step === "choose" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {BULK_ACTIONS.map((a) => {
              const Icon = a.icon;
              const disabled = a.kind !== "refresh_inventory" && !canAdmin;
              return (
                <button
                  key={a.kind}
                  onClick={() => chooseAction(a)}
                  disabled={disabled}
                  data-testid={`bulk-action-${a.kind}`}
                  className={`text-left rounded-xl border border-border bg-card p-3 hover:border-primary/60 hover:bg-primary/5 transition ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
                >
                  <div className="flex items-center gap-2">
                    <span className="h-8 w-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center"><Icon className="h-4 w-4" /></span>
                    <div className="font-medium text-sm">{a.label}</div>
                    <ChevronRight className="h-4 w-4 text-muted-foreground ml-auto" />
                  </div>
                </button>
              );
            })}
          </div>
        )}

        {step === "configure" && action && (
          <div className="space-y-4">
            <div className="rounded-xl border border-border bg-foreground/[0.02] p-3 text-xs">
              This will run <b>{action.label}</b> on <b>{selectedDevices.length}</b> device(s).
            </div>
            {(action.params || []).map((p) => (
              <div key={p.name}>
                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">
                  {p.label}{p.required && <span className="text-red-400"> *</span>}
                </div>
                {p.type === "textarea" ? (
                  <Textarea rows={5} className="font-mono text-xs"
                    value={params[p.name] || ""}
                    onChange={(e) => setParams({ ...params, [p.name]: e.target.value })}
                    placeholder={p.placeholder}
                    data-testid={`bulk-param-${p.name}`} />
                ) : p.type === "select" ? (
                  <select className="w-full h-9 rounded-md border border-border bg-foreground/[0.03] px-3 text-sm"
                    value={params[p.name] || p.defaultValue || ""}
                    onChange={(e) => setParams({ ...params, [p.name]: e.target.value })}
                    data-testid={`bulk-param-${p.name}`}>
                    {p.options.map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <Input value={params[p.name] || ""} onChange={(e) => setParams({ ...params, [p.name]: e.target.value })}
                    placeholder={p.placeholder} data-testid={`bulk-param-${p.name}`} />
                )}
              </div>
            ))}
            {action.requiresConfirm && (
              <div>
                <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">
                  Type <span className="font-mono text-foreground">CONFIRM</span> to proceed
                </div>
                <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)}
                  placeholder="CONFIRM" data-testid="bulk-confirm-input" />
              </div>
            )}
            <div className="max-h-32 overflow-auto rounded-lg border border-border p-2 text-xs text-muted-foreground">
              {selectedDevices.map((d) => (
                <div key={d.id} className="flex items-center justify-between py-0.5">
                  <span>{d.display_name || d.hostname}</span>
                  <span className="font-mono text-[10px] text-muted-foreground/70">{d.id.slice(0, 8)}</span>
                </div>
              ))}
            </div>
            {error && <div className="text-xs text-red-300 rounded-lg border border-red-500/30 bg-red-500/10 p-2">{error}</div>}
            <DialogFooter>
              <Button variant="secondary" onClick={() => setStep("choose")}>Back</Button>
              <Button onClick={submit} disabled={!canSubmit}
                className={action.tone === "critical" ? "bg-red-500 hover:bg-red-600 text-white" : ""}
                data-testid="bulk-submit-button">
                Run on {selectedDevices.length} device{selectedDevices.length !== 1 ? "s" : ""}
              </Button>
            </DialogFooter>
          </div>
        )}

        {(step === "running" || step === "summary") && batch && (
          <BatchProgress batch={batch} onRetry={retry} step={step} onClose={() => onOpenChange(false)} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function BatchProgress({ batch, onRetry, step, onClose }) {
  const c = batch.status_counts || {};
  const total = c.total || batch.total || (batch.actions || []).length;
  const done = (c.succeeded || 0) + (c.failed || 0) + (c.cancelled || 0) + (c.expired || 0);
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-border bg-foreground/[0.02] p-3">
        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">Progress</span>
          <span className="ml-auto font-mono tabular-nums" data-testid="bulk-progress">{done}/{total}</span>
        </div>
        <div className="mt-2 h-1.5 rounded-full bg-foreground/[0.05] overflow-hidden">
          <motion.div className="h-full bg-primary" animate={{ width: `${pct}%` }} />
        </div>
        <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
          <StatBadge variant="info">{c.pending || 0} pending</StatBadge>
          <StatBadge variant="warning">{c.in_progress || 0} running</StatBadge>
          <StatBadge variant="healthy">{c.succeeded || 0} succeeded</StatBadge>
          <StatBadge variant="critical">{c.failed || 0} failed</StatBadge>
          {(c.expired || 0) > 0 && <StatBadge variant="offline">{c.expired} expired</StatBadge>}
        </div>
      </div>
      <div className="max-h-64 overflow-auto rounded-xl border border-border">
        <AnimatePresence initial={false}>
          {(batch.actions || []).map((a) => {
            const Icon = STATUS_ICON[a.status] || Clock;
            const isTerminal = ["succeeded", "failed", "cancelled", "expired"].includes(a.status);
            return (
              <motion.div key={a.id} layout
                className="flex items-center gap-2 p-2 border-b border-border last:border-b-0">
                <Icon className={`h-4 w-4 ${a.status === "in_progress" ? "animate-spin text-amber-400" : a.status === "succeeded" ? "text-emerald-400" : a.status === "failed" ? "text-red-400" : "text-muted-foreground"}`} />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium truncate">{a.device_hostname || a.device_display_name || a.device_id?.slice(0, 8)}</div>
                  {a.error && <div className="text-[10px] text-red-300 truncate">{a.error}</div>}
                </div>
                <StatBadge variant={STATUS_TO_VARIANT[a.status] || "info"}>{a.status}</StatBadge>
                {isTerminal && a.status !== "succeeded" && (
                  <Button size="sm" variant="outline" onClick={() => onRetry(a.id)} data-testid={`bulk-retry-${a.id}`}>
                    <RotateCcw className="h-3 w-3 mr-1" /> Retry
                  </Button>
                )}
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
      <DialogFooter>
        <Button variant="secondary" onClick={onClose}>{step === "summary" ? "Close" : "Run in background"}</Button>
      </DialogFooter>
    </div>
  );
}

export default BulkActionsDialog;
