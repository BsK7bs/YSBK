import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Building2 } from "lucide-react";
import { api } from "../lib/api";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Button } from "../components/ui/button";
import { Switch } from "../components/ui/switch";
import { useAuth } from "../contexts/AuthContext";
import { hasRole, extractError } from "../lib/format";

export default function OrgSettingsPage() {
  const { organization, refreshMe, user } = useAuth();
  const canEdit = hasRole(user, "admin");
  const [form, setForm] = useState({
    name: organization?.name || "",
    logo_url: organization?.logo_url || "",
    timezone: organization?.timezone || "UTC",
    notify_email: organization?.notification_prefs?.email !== false,
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (organization) {
      setForm({
        name: organization.name || "",
        logo_url: organization.logo_url || "",
        timezone: organization.timezone || "UTC",
        notify_email: organization.notification_prefs?.email !== false,
      });
    }
  }, [organization]);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.patch("/org", {
        name: form.name,
        logo_url: form.logo_url || null,
        timezone: form.timezone,
        notification_prefs: { email: form.notify_email },
      });
      toast.success("Organization updated");
      await refreshMe();
    } catch (err) {
      toast.error(extractError(err, "Failed to update organization"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold tracking-tight">Organization Settings</div>
        <div className="mt-1 text-sm text-muted-foreground">Manage your organization’s profile and notification preferences.</div>
      </div>

      <form onSubmit={submit} className="rounded-2xl border border-border bg-card p-5 sm:p-6 space-y-5 max-w-2xl">
        <div className="flex items-center gap-3 pb-3 border-b border-border">
          <div className="h-10 w-10 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center">
            <Building2 className="h-4 w-4 text-primary" />
          </div>
          <div className="text-sm font-semibold">Profile</div>
        </div>
        <div>
          <Label htmlFor="org-name">Organization name</Label>
          <Input id="org-name" required value={form.name} disabled={!canEdit} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} className="mt-1.5" data-testid="org-name-input" />
        </div>
        <div>
          <Label htmlFor="org-logo">Logo URL (optional)</Label>
          <Input id="org-logo" placeholder="https://…/logo.png" value={form.logo_url} disabled={!canEdit} onChange={(e) => setForm((f) => ({ ...f, logo_url: e.target.value }))} className="mt-1.5" />
        </div>
        <div>
          <Label htmlFor="org-tz">Time zone</Label>
          <Input id="org-tz" placeholder="UTC / America/New_York…" value={form.timezone} disabled={!canEdit} onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))} className="mt-1.5" data-testid="org-timezone-input" />
        </div>
        <div className="pt-3 border-t border-border">
          <div className="text-sm font-semibold mb-3">Notification preferences</div>
          <div className="flex items-center justify-between rounded-xl border border-border bg-foreground/[0.02] p-3">
            <div>
              <div className="text-sm font-medium">Email alerts</div>
              <div className="text-xs text-muted-foreground">Receive email digests for critical alerts.</div>
            </div>
            <Switch checked={form.notify_email} disabled={!canEdit} onCheckedChange={(v) => setForm((f) => ({ ...f, notify_email: v }))} data-testid="org-notify-email-switch" />
          </div>
        </div>
        {canEdit && (
          <div className="pt-2">
            <Button type="submit" disabled={loading} data-testid="org-save-button">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save changes"}
            </Button>
          </div>
        )}
        {!canEdit && <div className="text-xs text-muted-foreground">Requires Admin role to edit.</div>}
      </form>
    </div>
  );
}
