import React, { useState } from "react";
import { toast } from "sonner";
import { Loader2, MonitorSmartphone } from "lucide-react";
import { api } from "../lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/dialog";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { extractError } from "../lib/format";

const INITIAL = {
  hostname: "",
  display_name: "",
  ip_address: "",
  mac_address: "",
  serial_number: "",
  os_name: "",
  os_version: "",
  cpu: "",
  ram_gb: "",
  disk_gb: "",
  motherboard: "",
  bios_version: "",
  notes: "",
  tags: "",
};

function Field({ id, label, hint, error, className, children }) {
  return (
    <div className={className}>
      <Label htmlFor={id} className="text-xs uppercase tracking-widest text-muted-foreground">{label}</Label>
      <div className="mt-1.5">{children}</div>
      {hint && !error && <div className="mt-1 text-[11px] text-muted-foreground">{hint}</div>}
      {error && <div className="mt-1 text-[11px] text-red-400">{error}</div>}
    </div>
  );
}

export default function RegisterComputerDialog({ open, onOpenChange, onRegistered }) {
  const [form, setForm] = useState(INITIAL);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e?.target?.value ?? e }));

  const reset = () => {
    setForm(INITIAL);
    setErrors({});
  };

  const submit = async (e) => {
    e.preventDefault();
    setErrors({});
    const errs = {};
    if (!form.hostname.trim()) errs.hostname = "Hostname is required";
    if (form.mac_address && !/^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$/.test(form.mac_address.trim())) {
      errs.mac_address = "Must look like AA:BB:CC:DD:EE:FF";
    }
    if (form.ip_address && !/^(\d{1,3}\.){3}\d{1,3}$|:/.test(form.ip_address.trim())) {
      errs.ip_address = "Enter a valid IPv4 or IPv6 address";
    }
    if (form.ram_gb && Number.isNaN(Number(form.ram_gb))) errs.ram_gb = "Must be a number";
    if (form.disk_gb && Number.isNaN(Number(form.disk_gb))) errs.disk_gb = "Must be a number";
    if (Object.keys(errs).length) {
      setErrors(errs);
      return;
    }
    setLoading(true);
    try {
      const body = {
        hostname: form.hostname.trim(),
        display_name: form.display_name.trim() || null,
        ip_address: form.ip_address.trim() || null,
        mac_address: form.mac_address.trim() || null,
        serial_number: form.serial_number.trim() || null,
        os_name: form.os_name.trim() || null,
        os_version: form.os_version.trim() || null,
        cpu: form.cpu.trim() || null,
        ram_gb: form.ram_gb ? Number(form.ram_gb) : null,
        disk_gb: form.disk_gb ? Number(form.disk_gb) : null,
        motherboard: form.motherboard.trim() || null,
        bios_version: form.bios_version.trim() || null,
        notes: form.notes.trim() || null,
        tags: form.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      };
      const r = await api.post("/devices", body);
      onRegistered?.(r.data);
      reset();
      onOpenChange(false);
    } catch (err) {
      toast.error(extractError(err, "Failed to register computer"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) reset(); onOpenChange(v); }}>
      <DialogContent className="sm:max-w-2xl glass" data-testid="register-computer-dialog">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center">
              <MonitorSmartphone className="h-4 w-4 text-primary" />
            </div>
            <div>
              <DialogTitle>Register a computer</DialogTitle>
              <DialogDescription>
                Add a computer to your inventory manually. You can attach a live agent later using an enrollment code.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-5 max-h-[70vh] overflow-y-auto pr-1">
          <section>
            <div className="text-xs font-semibold tracking-widest text-muted-foreground uppercase mb-3">Identity</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field id="reg-hostname" label="Hostname" error={errors.hostname}>
                <Input id="reg-hostname" required value={form.hostname} onChange={set("hostname")} placeholder="LAB-PC-01" data-testid="reg-hostname" />
              </Field>
              <Field id="reg-display" label="Display name" hint="Optional friendly name">
                <Input id="reg-display" value={form.display_name} onChange={set("display_name")} placeholder="Lab · iMac #3" />
              </Field>
              <Field id="reg-serial" label="Serial number" hint="Unique per computer">
                <Input id="reg-serial" value={form.serial_number} onChange={set("serial_number")} placeholder="C02XG1234ABC" data-testid="reg-serial" />
              </Field>
              <Field id="reg-tags" label="Tags" hint="Comma-separated, e.g. lab, math-dept">
                <Input id="reg-tags" value={form.tags} onChange={set("tags")} placeholder="lab, floor-2" />
              </Field>
            </div>
          </section>

          <section>
            <div className="text-xs font-semibold tracking-widest text-muted-foreground uppercase mb-3">Network</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field id="reg-ip" label="IP address" error={errors.ip_address}>
                <Input id="reg-ip" value={form.ip_address} onChange={set("ip_address")} placeholder="192.168.1.42" data-testid="reg-ip" />
              </Field>
              <Field id="reg-mac" label="MAC address" error={errors.mac_address}>
                <Input id="reg-mac" value={form.mac_address} onChange={set("mac_address")} placeholder="AA:BB:CC:DD:EE:FF" data-testid="reg-mac" />
              </Field>
            </div>
          </section>

          <section>
            <div className="text-xs font-semibold tracking-widest text-muted-foreground uppercase mb-3">Operating System</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field id="reg-os" label="OS name">
                <Input id="reg-os" value={form.os_name} onChange={set("os_name")} placeholder="Windows 11 Pro" data-testid="reg-os" />
              </Field>
              <Field id="reg-osv" label="OS version">
                <Input id="reg-osv" value={form.os_version} onChange={set("os_version")} placeholder="23H2 (Build 22631)" />
              </Field>
            </div>
          </section>

          <section>
            <div className="text-xs font-semibold tracking-widest text-muted-foreground uppercase mb-3">Hardware</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field id="reg-cpu" label="CPU">
                <Input id="reg-cpu" value={form.cpu} onChange={set("cpu")} placeholder="Intel Core i7-1165G7" data-testid="reg-cpu" />
              </Field>
              <Field id="reg-ram" label="RAM (GB)" error={errors.ram_gb}>
                <Input id="reg-ram" type="number" step="0.5" min="0" value={form.ram_gb} onChange={set("ram_gb")} placeholder="16" data-testid="reg-ram" />
              </Field>
              <Field id="reg-disk" label="Disk (GB)" error={errors.disk_gb}>
                <Input id="reg-disk" type="number" step="1" min="0" value={form.disk_gb} onChange={set("disk_gb")} placeholder="512" data-testid="reg-disk" />
              </Field>
              <Field id="reg-mb" label="Motherboard">
                <Input id="reg-mb" value={form.motherboard} onChange={set("motherboard")} placeholder="Dell 0A1B2C" data-testid="reg-motherboard" />
              </Field>
              <Field id="reg-bios" label="BIOS version" className="sm:col-span-2">
                <Input id="reg-bios" value={form.bios_version} onChange={set("bios_version")} placeholder="2.15.0" data-testid="reg-bios" />
              </Field>
            </div>
          </section>

          <section>
            <div className="text-xs font-semibold tracking-widest text-muted-foreground uppercase mb-3">Notes</div>
            <Textarea rows={3} value={form.notes} onChange={set("notes")} placeholder="Any relevant maintenance notes, warranty info, or location details…" data-testid="reg-notes" />
          </section>

          <DialogFooter className="!mt-6 pt-4 border-t border-border">
            <Button type="button" variant="secondary" onClick={() => { reset(); onOpenChange(false); }} disabled={loading}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading} data-testid="reg-submit-button">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Register computer"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
