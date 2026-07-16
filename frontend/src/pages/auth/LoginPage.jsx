import { extractError } from "../../lib/format";
import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Cpu, Loader2, Eye, EyeOff } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Checkbox } from "../../components/ui/checkbox";
import { useAuth } from "../../contexts/AuthContext";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    try {
      await login(email, password, remember);
      toast.success("Welcome back!");
      navigate("/app/dashboard");
    } catch (err) {
      const detail = extractError(err, "Sign-in failed");
      toast.error(detail);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full grid lg:grid-cols-2">
      {/* Left brand */}
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
          <div className="text-3xl font-semibold tracking-tight max-w-md">Every device, mirrored. Every problem, prevented.</div>
          <div className="mt-3 text-sm text-muted-foreground max-w-md">
            A modern IT operations console for schools, MSPs, and enterprise teams. Real-time telemetry, health scores, remote actions.
          </div>
        </div>
        <div className="text-xs text-muted-foreground">© Digital Twin Platform</div>
      </div>

      {/* Right form */}
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <div className="h-9 w-9 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center">
              <Cpu className="h-4 w-4 text-primary" />
            </div>
            <div className="text-sm font-semibold">Digital Twin Platform</div>
          </div>
          <div className="text-2xl font-semibold tracking-tight">Sign in</div>
          <div className="mt-1 text-sm text-muted-foreground">Welcome back — access your organization.</div>

          <form onSubmit={submit} className="mt-8 space-y-5">
            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                data-testid="login-email-input"
                className="mt-1.5"
                placeholder="you@company.com"
              />
            </div>
            <div>
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Password</Label>
                <button type="button" onClick={() => setShow((s) => !s)} className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
                  {show ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />} {show ? "Hide" : "Show"}
                </button>
              </div>
              <Input
                id="password"
                type={show ? "text" : "password"}
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                data-testid="login-password-input"
                className="mt-1.5"
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox id="remember" checked={remember} onCheckedChange={setRemember} data-testid="login-remember-checkbox" />
              <Label htmlFor="remember" className="text-sm text-muted-foreground">Keep me signed in</Label>
            </div>
            <Button type="submit" className="w-full h-11" disabled={loading} data-testid="login-submit-button">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Sign in"}
            </Button>
          </form>

          <div className="mt-6 text-sm text-muted-foreground">
            Don’t have an account?{" "}
            <Link to="/signup" className="text-foreground font-medium underline underline-offset-4">Create one</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
