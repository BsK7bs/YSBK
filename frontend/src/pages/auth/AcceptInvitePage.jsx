import { extractError } from "../../lib/format";
import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Cpu, Loader2 } from "lucide-react";
import { api } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { useAuth } from "../../contexts/AuthContext";

export default function AcceptInvitePage() {
  const { token } = useParams();
  const navigate = useNavigate();
  const { acceptInvitation } = useAuth();
  const [invitation, setInvitation] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [full_name, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api
      .get(`/invitations/lookup/${token}`)
      .then((r) => setInvitation(r.data))
      .catch(() => setNotFound(true));
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    if (loading) return;
    if (password.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    setLoading(true);
    try {
      await acceptInvitation(token, full_name, password);
      toast.success("Welcome to the team!");
      navigate("/app/dashboard");
    } catch (err) {
      toast.error(extractError(err, "Failed to accept invitation"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-3 mb-8">
          <div className="h-9 w-9 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center">
            <Cpu className="h-4 w-4 text-primary" />
          </div>
          <div className="text-sm font-semibold">Digital Twin Platform</div>
        </div>

        {notFound && (
          <div className="rounded-2xl border border-border bg-card p-6">
            <div className="text-lg font-semibold">Invitation not found</div>
            <div className="mt-2 text-sm text-muted-foreground">
              This invitation link is invalid, already used, or expired. Ask your admin to resend it.
            </div>
          </div>
        )}

        {!notFound && !invitation && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading invitation…
          </div>
        )}

        {invitation && (
          <>
            <div className="text-2xl font-semibold tracking-tight">You’re invited</div>
            <div className="mt-1 text-sm text-muted-foreground">
              Join <span className="text-foreground font-medium">{invitation.organization?.name}</span> as{" "}
              <span className="text-foreground font-medium capitalize">{invitation.role}</span>.
            </div>
            <form onSubmit={submit} className="mt-8 space-y-4">
              <div>
                <Label>Email</Label>
                <Input value={invitation.email} disabled className="mt-1.5" />
              </div>
              <div>
                <Label htmlFor="name">Full name</Label>
                <Input
                  id="name"
                  required
                  value={full_name}
                  onChange={(e) => setFullName(e.target.value)}
                  className="mt-1.5"
                  data-testid="invite-name-input"
                />
              </div>
              <div>
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="mt-1.5"
                  data-testid="invite-password-input"
                />
              </div>
              <Button type="submit" disabled={loading} className="w-full h-11" data-testid="invite-submit-button">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Accept invitation"}
              </Button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
