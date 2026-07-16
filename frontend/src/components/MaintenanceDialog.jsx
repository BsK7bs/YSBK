import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Wrench, ShieldCheck, X, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "./ui/dialog";
import { StatBadge } from "./StatBadge";

export function MaintenanceDialog({ open, onOpenChange, device, onChanged }) {
  const [duration, setDuration] = useState(60);
  const [reason, setReason] = useState("");
  const [suppress, setSuppress] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setDuration(60); setReason(""); setSuppress(true); }
  }, [open]);

  const inMaintenance = device?.maintenance_mode;

  const enable = async () => {
    setBusy(true);
    try {
      await api.post(`/devices/${device.id}/maintenance/enable`, {
        duration_minutes: Number(duration),
        reason,
        suppress_alerts: suppress,
      });
      toast.success(`Maintenance mode enabled for ${duration} min`);
      onChanged?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to enable maintenance");
    } finally { setBusy(false); }
  };

  const disable = async () => {
    setBusy(true);
    try {
      await api.post(`/devices/${device.id}/maintenance/disable`);
      toast.success("Maintenance mode disabled");
      onChanged?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to disable maintenance");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="maintenance-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wrench className="h-4 w-4 text-amber-400" />
            Maintenance mode
          </DialogTitle>
          <DialogDescription>
            Suppress alerts on <b>{device?.display_name || device?.hostname}</b> while you perform planned work.
          </DialogDescription>
        </DialogHeader>

        {inMaintenance ? (
          <div className="space-y-3">
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
              This device is currently in maintenance mode.
              {device.maintenance_ends_at && <div className="text-xs mt-1 text-muted-foreground">Ends: {new Date(device.maintenance_ends_at).toLocaleString()}</div>}
              {device.maintenance_reason && <div className="text-xs mt-1 italic">“{device.maintenance_reason}”</div>}
            </div>
            <DialogFooter>
              <Button variant="secondary" onClick={() => onOpenChange(false)}>Close</Button>
              <Button variant="outline" onClick={disable} disabled={busy} data-testid="maintenance-disable-btn">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <><X className="h-4 w-4 mr-1" /> Exit maintenance</>}
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-3">
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Duration (minutes)</div>
              <Input type="number" min={1} max={43200} value={duration} onChange={(e) => setDuration(e.target.value)} data-testid="maintenance-duration-input" />
              <div className="mt-1 text-[10px] text-muted-foreground">Auto-exits when the window elapses. Max 30 days.</div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Reason (optional)</div>
              <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Windows update rollout, RAM swap, hardware move..." data-testid="maintenance-reason-input" />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={suppress} onChange={(e) => setSuppress(e.target.checked)} />
              <ShieldCheck className="h-4 w-4 text-emerald-400" /> Suppress alerts while in maintenance
            </label>
            <DialogFooter>
              <Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button onClick={enable} disabled={busy} data-testid="maintenance-enable-btn">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Enter maintenance"}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function MaintenanceBadge({ device, className = "" }) {
  if (!device?.maintenance_mode) return null;
  return (
    <StatBadge variant="warning" className={className}>
      <Wrench className="h-3 w-3 mr-1 inline" />
      Maintenance
    </StatBadge>
  );
}

export default MaintenanceDialog;
