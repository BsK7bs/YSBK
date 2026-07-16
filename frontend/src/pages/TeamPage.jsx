import React, { useCallback, useEffect, useState } from "react";
import { Users, UserPlus, Copy, Trash2, ShieldCheck, Loader2, Mail } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { EmptyState } from "../components/EmptyState";
import { StatBadge } from "../components/StatBadge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "../components/ui/alert-dialog";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { formatRelative, hasRole, ROLE_LABELS, copyToClipboard, extractError } from "../lib/format";
import { useAuth } from "../contexts/AuthContext";

function inviteLink(token) {
  return `${window.location.origin}/invite/${token}`;
}

export default function TeamPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState(null);
  const [invites, setInvites] = useState([]);
  const [openInvite, setOpenInvite] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: "", role: "viewer" });
  const [inviteLoading, setInviteLoading] = useState(false);
  const [pendingInvite, setPendingInvite] = useState(null);
  const canAdmin = hasRole(user, "admin");

  const load = useCallback(async () => {
    try {
      const uReq = api.get("/users");
      const iReq = canAdmin ? api.get("/invitations") : Promise.resolve({ data: [] });
      const [u, i] = await Promise.all([uReq, iReq]);
      setUsers(u.data || []);
      setInvites(i.data || []);
    } catch {}
  }, [canAdmin]);

  useEffect(() => {
    load();
  }, [load]);

  const sendInvite = async (e) => {
    e.preventDefault();
    setInviteLoading(true);
    try {
      const r = await api.post("/invitations", inviteForm);
      const link = inviteLink(r.data.invitation.token);
      setPendingInvite({ ...r.data.invitation, link });
      toast.success("Invitation created");
      setInviteForm({ email: "", role: "viewer" });
      load();
    } catch (err) {
      toast.error(extractError(err, "Failed to send invite"));
    } finally {
      setInviteLoading(false);
    }
  };

  const changeRole = async (userId, role) => {
    try {
      await api.patch(`/users/${userId}/role`, { role });
      toast.success("Role updated");
      load();
    } catch (err) {
      toast.error(extractError(err, "Failed to update role"));
    }
  };

  const removeUser = async (userId) => {
    try {
      await api.delete(`/users/${userId}`);
      toast.success("User removed");
      load();
    } catch (err) {
      toast.error(extractError(err, "Failed to remove"));
    }
  };

  const revokeInvite = async (id) => {
    try {
      await api.delete(`/invitations/${id}`);
      toast.success("Invitation revoked");
      load();
    } catch (err) {
      toast.error(extractError(err, "Failed"));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-2xl font-semibold tracking-tight">Team</div>
          <div className="mt-1 text-sm text-muted-foreground">Members of your organization and pending invitations.</div>
        </div>
        {canAdmin && (
          <Button onClick={() => setOpenInvite(true)} data-testid="team-invite-button">
            <UserPlus className="h-4 w-4" /> Invite member
          </Button>
        )}
      </div>

      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-4 border-b border-border text-sm font-semibold">Members</div>
        {users === null ? (
          <div className="p-6 text-sm text-muted-foreground">Loading…</div>
        ) : users.length === 0 ? (
          <div className="p-6">
            <EmptyState icon={Users} title="You’re the only member" description="Invite technicians and viewers to collaborate." primaryAction={canAdmin ? () => setOpenInvite(true) : undefined} primaryLabel="Invite a member" />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-background/60 border-b border-border">
              <tr className="text-left text-xs text-muted-foreground">
                <th className="px-5 py-3 font-medium">Name</th>
                <th className="px-3 py-3 font-medium">Email</th>
                <th className="px-3 py-3 font-medium">Role</th>
                <th className="px-3 py-3 font-medium">Joined</th>
                {canAdmin && <th className="px-3 py-3 font-medium text-right">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-border hover:bg-foreground/[0.02]">
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-3">
                      <div className="h-8 w-8 rounded-full bg-gradient-to-br from-primary/40 to-cyan-500/40 flex items-center justify-center text-xs font-semibold">
                        {(u.full_name || u.email).charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <div className="font-medium">{u.full_name}</div>
                        {u.id === user?.id && <div className="text-[11px] text-muted-foreground">You</div>}
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-3 text-muted-foreground">{u.email}</td>
                  <td className="px-3 py-3">
                    {canAdmin && u.id !== user?.id && u.role !== "owner" ? (
                      <Select value={u.role} onValueChange={(v) => changeRole(u.id, v)}>
                        <SelectTrigger className="h-8 w-[130px] text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="viewer">Viewer</SelectItem>
                          <SelectItem value="technician">Technician</SelectItem>
                          <SelectItem value="admin">Admin</SelectItem>
                          {user?.role === "owner" && <SelectItem value="owner">Owner</SelectItem>}
                        </SelectContent>
                      </Select>
                    ) : (
                      <StatBadge variant={u.role === "owner" ? "info" : "info"}>{ROLE_LABELS[u.role]}</StatBadge>
                    )}
                  </td>
                  <td className="px-3 py-3 text-muted-foreground">{formatRelative(u.created_at)}</td>
                  {canAdmin && (
                    <td className="px-3 py-3 text-right">
                      {u.role !== "owner" && u.id !== user?.id ? (
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <button className="text-xs text-red-400 hover:underline inline-flex items-center gap-1" data-testid="team-remove-button">
                              <Trash2 className="h-3 w-3" /> Remove
                            </button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Remove {u.full_name}?</AlertDialogTitle>
                              <AlertDialogDescription>They will lose access to the organization immediately.</AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Cancel</AlertDialogCancel>
                              <AlertDialogAction onClick={() => removeUser(u.id)}>Remove</AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {canAdmin && (
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <div className="px-5 py-4 border-b border-border text-sm font-semibold">Pending invitations</div>
          {invites.length === 0 ? (
            <div className="p-6 text-sm text-muted-foreground">No pending invitations.</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-background/60 border-b border-border">
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="px-5 py-3 font-medium">Email</th>
                  <th className="px-3 py-3 font-medium">Role</th>
                  <th className="px-3 py-3 font-medium">Created</th>
                  <th className="px-3 py-3 font-medium">Status</th>
                  <th className="px-3 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {invites.map((i) => (
                  <tr key={i.id} className="border-t border-border">
                    <td className="px-5 py-3">{i.email}</td>
                    <td className="px-3 py-3"><StatBadge variant="info">{ROLE_LABELS[i.role]}</StatBadge></td>
                    <td className="px-3 py-3 text-muted-foreground">{formatRelative(i.created_at)}</td>
                    <td className="px-3 py-3">
                      {i.accepted ? <StatBadge variant="healthy">Accepted</StatBadge> : <StatBadge variant="warning">Pending</StatBadge>}
                    </td>
                    <td className="px-3 py-3 text-right whitespace-nowrap">
                      <button
                        onClick={async () => {
                          const ok = await copyToClipboard(inviteLink(i.token));
                          ok ? toast.success("Invitation link copied") : toast.error("Copy failed");
                        }}
                        className="text-xs text-primary hover:underline mr-3 inline-flex items-center gap-1"
                      >
                        <Copy className="h-3 w-3" /> Copy link
                      </button>
                      {!i.accepted && (
                        <button onClick={() => revokeInvite(i.id)} className="text-xs text-red-400 hover:underline inline-flex items-center gap-1">
                          <Trash2 className="h-3 w-3" /> Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <Dialog open={openInvite} onOpenChange={setOpenInvite}>
        <DialogContent className="sm:max-w-md glass">
          <DialogHeader>
            <DialogTitle>Invite a team member</DialogTitle>
            <DialogDescription>They’ll receive a link to accept the invitation and create their account.</DialogDescription>
          </DialogHeader>
          {pendingInvite ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-3 text-sm text-emerald-300 flex items-start gap-2">
                <Mail className="h-4 w-4 mt-0.5" />
                <div>Send this link to <span className="font-medium">{pendingInvite.email}</span>. It’s valid for 7 days.</div>
              </div>
              <div className="rounded-xl border border-border bg-foreground/[0.03] p-3 flex items-center gap-2">
                <div className="text-xs font-mono truncate flex-1" data-testid="invite-link">{pendingInvite.link}</div>
                <button onClick={async () => { const ok = await copyToClipboard(pendingInvite.link); ok ? toast.success("Copied") : toast.error("Copy failed"); }} className="text-primary text-sm inline-flex items-center gap-1">
                  <Copy className="h-3 w-3" /> Copy
                </button>
              </div>
              <DialogFooter>
                <Button variant="secondary" onClick={() => { setPendingInvite(null); }}>Invite another</Button>
                <Button onClick={() => { setOpenInvite(false); setPendingInvite(null); }}>Done</Button>
              </DialogFooter>
            </div>
          ) : (
            <form onSubmit={sendInvite} className="space-y-4">
              <div>
                <Label htmlFor="invite-email">Email</Label>
                <Input id="invite-email" type="email" required value={inviteForm.email} onChange={(e) => setInviteForm((f) => ({ ...f, email: e.target.value }))} className="mt-1.5" data-testid="invite-email-input" />
              </div>
              <div>
                <Label>Role</Label>
                <Select value={inviteForm.role} onValueChange={(v) => setInviteForm((f) => ({ ...f, role: v }))}>
                  <SelectTrigger className="mt-1.5" data-testid="invite-role-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="viewer">Viewer — Read only</SelectItem>
                    <SelectItem value="technician">Technician — View + Actions</SelectItem>
                    <SelectItem value="admin">Admin — Full management</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <DialogFooter>
                <Button variant="secondary" onClick={() => setOpenInvite(false)} type="button">Cancel</Button>
                <Button type="submit" disabled={inviteLoading} data-testid="invite-submit">
                  {inviteLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create invitation"}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
