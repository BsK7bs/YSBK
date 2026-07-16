import React, { useState } from "react";
import { toast } from "sonner";
import { Loader2, User as UserIcon } from "lucide-react";
import { api } from "../lib/api";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Button } from "../components/ui/button";
import { useAuth } from "../contexts/AuthContext";
import { ROLE_LABELS, extractError } from "../lib/format";

export default function ProfilePage() {
  const { user, organization, logout } = useAuth();
  const [pw, setPw] = useState({ current_password: "", new_password: "", confirm: "" });
  const [loading, setLoading] = useState(false);

  const submitPw = async (e) => {
    e.preventDefault();
    if (pw.new_password !== pw.confirm) {
      toast.error("Passwords do not match");
      return;
    }
    if (pw.new_password.length < 8) {
      toast.error("New password must be at least 8 characters");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/change-password", { current_password: pw.current_password, new_password: pw.new_password });
      toast.success("Password changed. Please sign in again.");
      setTimeout(() => logout(), 800);
    } catch (err) {
      toast.error(extractError(err, "Failed to change password"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold tracking-tight">My Profile</div>
        <div className="mt-1 text-sm text-muted-foreground">Your account details and password.</div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-4xl">
        <div className="rounded-2xl border border-border bg-card p-5">
          <div className="flex items-center gap-3 pb-3 border-b border-border">
            <div className="h-10 w-10 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center">
              <UserIcon className="h-4 w-4 text-primary" />
            </div>
            <div className="text-sm font-semibold">Account</div>
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <dt className="text-muted-foreground">Name</dt>
            <dd className="font-medium">{user?.full_name}</dd>
            <dt className="text-muted-foreground">Email</dt>
            <dd className="break-all">{user?.email}</dd>
            <dt className="text-muted-foreground">Role</dt>
            <dd className="capitalize">{ROLE_LABELS[user?.role]}</dd>
            <dt className="text-muted-foreground">Organization</dt>
            <dd className="truncate">{organization?.name}</dd>
          </dl>
        </div>

        <form onSubmit={submitPw} className="rounded-2xl border border-border bg-card p-5 space-y-4">
          <div className="text-sm font-semibold pb-3 border-b border-border">Change password</div>
          <div>
            <Label htmlFor="cp">Current password</Label>
            <Input id="cp" type="password" required value={pw.current_password} onChange={(e) => setPw((v) => ({ ...v, current_password: e.target.value }))} className="mt-1.5" data-testid="current-password-input" />
          </div>
          <div>
            <Label htmlFor="np">New password</Label>
            <Input id="np" type="password" required minLength={8} value={pw.new_password} onChange={(e) => setPw((v) => ({ ...v, new_password: e.target.value }))} className="mt-1.5" data-testid="new-password-input" />
          </div>
          <div>
            <Label htmlFor="cp2">Confirm new password</Label>
            <Input id="cp2" type="password" required minLength={8} value={pw.confirm} onChange={(e) => setPw((v) => ({ ...v, confirm: e.target.value }))} className="mt-1.5" data-testid="confirm-password-input" />
          </div>
          <Button type="submit" disabled={loading} data-testid="change-password-button">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Update password"}
          </Button>
        </form>
      </div>
    </div>
  );
}
