import { extractError } from "../../lib/format";
import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Cpu, Loader2 } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { useAuth } from "../../contexts/AuthContext";

export default function SignupPage() {
  const [form, setForm] = useState({
    organization_name: "",
    full_name: "",
    email: "",
    password: "",
  });
  const [loading, setLoading] = useState(false);
  const { signup } = useAuth();
  const navigate = useNavigate();

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (loading) return;
    if (form.password.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    setLoading(true);
    try {
      await signup(form);
      toast.success("Organization created!");
      navigate("/app/dashboard");
    } catch (err) {
      const detail = extractError(err, "Sign up failed");
      toast.error(detail);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full grid lg:grid-cols-2">
      <div className="hidden lg:flex flex-col justify-between relative bg-card border-r border-border p-10">
        <div className="absolute inset-0 -z-10 opacity-70" style={{
          background: "linear-gradient(135deg, hsl(var(--primary) / 0.35), hsl(var(--info) / 0.18), transparent 70%)",
        }} />
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center">
            <Cpu className="h-4 w-4 text-primary" />
          </div>
          <div className="text-sm font-semibold">Digital Twin Platform</div>
        </div>
        <div>
          <div className="text-3xl font-semibold tracking-tight max-w-md">Deploy your fleet’s twin in minutes.</div>
          <div className="mt-3 text-sm text-muted-foreground max-w-md">
            Multi-tenant by design. Owner, admin, technician, and viewer roles. Data is fully isolated per organization.
          </div>
        </div>
        <div className="text-xs text-muted-foreground">Free to start · No credit card</div>
      </div>

      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <div className="h-9 w-9 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center">
              <Cpu className="h-4 w-4 text-primary" />
            </div>
            <div className="text-sm font-semibold">Digital Twin Platform</div>
          </div>
          <div className="text-2xl font-semibold tracking-tight">Create your organization</div>
          <div className="mt-1 text-sm text-muted-foreground">You’ll be the Owner and can invite your team.</div>

          <form onSubmit={submit} className="mt-8 space-y-4">
            <div>
              <Label htmlFor="org">Organization name</Label>
              <Input id="org" required value={form.organization_name} onChange={set("organization_name")} className="mt-1.5" data-testid="signup-org-input" placeholder="Acme IT" />
            </div>
            <div>
              <Label htmlFor="name">Full name</Label>
              <Input id="name" required value={form.full_name} onChange={set("full_name")} className="mt-1.5" data-testid="signup-name-input" placeholder="Ada Lovelace" />
            </div>
            <div>
              <Label htmlFor="email">Work email</Label>
              <Input id="email" type="email" required value={form.email} onChange={set("email")} className="mt-1.5" data-testid="signup-email-input" placeholder="you@company.com" />
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" required minLength={8} value={form.password} onChange={set("password")} className="mt-1.5" data-testid="signup-password-input" placeholder="At least 8 characters" />
            </div>
            <Button type="submit" className="w-full h-11" disabled={loading} data-testid="signup-submit-button">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create organization"}
            </Button>
          </form>

          <div className="mt-6 text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link to="/login" className="text-foreground font-medium underline underline-offset-4">Sign in</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
