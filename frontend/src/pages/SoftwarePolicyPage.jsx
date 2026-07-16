import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  BadgeCheck, Ban, Check, ChevronRight, Filter, HardDrive, ListFilter,
  Loader2, Package, PackageCheck, PackageMinus, PackagePlus, Plus,
  RefreshCw, Search, Shield, ShieldAlert, ShieldCheck, ShieldX, Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { EmptyState } from "../components/EmptyState";
import { StatBadge } from "../components/StatBadge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "../components/ui/dialog";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Label } from "../components/ui/label";
import { formatRelative, extractError, hasRole } from "../lib/format";
import { useAuth } from "../contexts/AuthContext";
import { cn } from "../lib/utils";

const MODE_META = {
  monitor:   { label: "Monitor Only", icon: Shield,       tone: "info", desc: "Inventory and reporting only. No enforcement." },
  blocklist: { label: "Blocklist Mode", icon: Ban,        tone: "critical", desc: "Anything on the blocklist raises a policy violation alert." },
  allowlist: { label: "Allowlist Mode", icon: ShieldCheck,tone: "healthy", desc: "Only approved software is allowed; anything else is flagged." },
};

function ScoreRing({ score, size = 96, thickness = 10 }) {
  const s = Math.max(0, Math.min(100, score ?? 0));
  const r = size / 2 - thickness;
  const c = 2 * Math.PI * r;
  const dash = (s / 100) * c;
  const color = s >= 90 ? "text-emerald-400" : s >= 75 ? "text-lime-400" : s >= 50 ? "text-amber-400" : "text-red-400";
  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size/2} cy={size/2} r={r} strokeWidth={thickness} className="stroke-current text-foreground/10" fill="none" />
        <circle cx={size/2} cy={size/2} r={r} strokeWidth={thickness} className={cn("stroke-current transition-all duration-700 ease-out", color)} strokeLinecap="round" strokeDasharray={`${dash} ${c}`} fill="none" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-xl font-semibold tabular-nums" data-testid="compliance-score-value">{Math.round(s)}</div>
        <div className="text-[10px] text-muted-foreground">score</div>
      </div>
    </div>
  );
}

function RuleForm({ mode, onSubmit }) {
  const [name, setName] = useState("");
  const [publisher, setPublisher] = useState("");
  const [category, setCategory] = useState("");
  const [severity, setSeverity] = useState("high");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        if (!name && !publisher) { toast.error("Name or publisher is required"); return; }
        setBusy(true);
        try {
          await onSubmit({ mode, name, publisher, category: category || undefined, severity_override: severity, notes });
          setName(""); setPublisher(""); setCategory(""); setNotes("");
        } catch (err) { toast.error(extractError(err, "Failed")); }
        finally { setBusy(false); }
      }}
      className="grid grid-cols-1 md:grid-cols-2 gap-3"
      data-testid={`software-rule-form-${mode}`}
    >
      <div>
        <Label>Software name</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. uTorrent" data-testid={`software-rule-name-${mode}`} />
      </div>
      <div>
        <Label>Publisher</Label>
        <Input value={publisher} onChange={(e) => setPublisher(e.target.value)} placeholder="e.g. BitTorrent, Inc." data-testid={`software-rule-publisher-${mode}`} />
      </div>
      <div>
        <Label>Category (optional)</Label>
        <Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. Utilities" />
      </div>
      <div>
        <Label>Alert severity override</Label>
        <Select value={severity} onValueChange={setSeverity}>
          <SelectTrigger data-testid={`software-rule-severity-${mode}`}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="critical">Critical</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="low">Low</SelectItem>
            <SelectItem value="info">Info</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="md:col-span-2">
        <Label>Notes</Label>
        <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Reason or reference ticket" />
      </div>
      <div className="md:col-span-2 flex justify-end">
        <Button type="submit" disabled={busy} data-testid={`software-rule-submit-${mode}`}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Plus className="h-4 w-4 mr-1" />}
          Add rule
        </Button>
      </div>
    </form>
  );
}

function RulesTable({ rules, onDelete, canAct, mode }) {
  if (!rules?.length) {
    return <EmptyState icon={mode === "allow" ? PackageCheck : PackageMinus} title={`No ${mode === "allow" ? "approved" : "blocked"} software rules yet`} description="Add rules above to enforce your policy." />;
  }
  return (
    <div className="rounded-2xl border border-border bg-card overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-background/60 border-b border-border">
          <tr className="text-left text-xs text-muted-foreground">
            <th className="px-4 py-3 font-medium">Name</th>
            <th className="px-3 py-3 font-medium">Publisher</th>
            <th className="px-3 py-3 font-medium">Category</th>
            <th className="px-3 py-3 font-medium">Severity</th>
            <th className="px-3 py-3 font-medium">Added</th>
            {canAct && <th className="px-3 py-3 font-medium text-right">Actions</th>}
          </tr>
        </thead>
        <tbody>
          {rules.map((r) => (
            <tr key={r.id} className="border-t border-border hover:bg-foreground/[0.02]" data-testid={`software-rule-row-${r.id}`}>
              <td className="px-4 py-2 font-medium">{r.name || "—"}</td>
              <td className="px-3 py-2 text-muted-foreground">{r.publisher || "—"}</td>
              <td className="px-3 py-2 text-muted-foreground">{r.category || "—"}</td>
              <td className="px-3 py-2"><StatBadge variant={r.severity_override === "critical" ? "critical" : r.severity_override === "high" ? "high-risk" : r.severity_override === "medium" ? "warning" : "info"}>{r.severity_override || "high"}</StatBadge></td>
              <td className="px-3 py-2 text-muted-foreground text-xs">{formatRelative(r.created_at)}</td>
              {canAct && (
                <td className="px-3 py-2 text-right">
                  <button
                    onClick={() => onDelete(r.id)}
                    className="text-xs text-red-300 hover:underline inline-flex items-center gap-1"
                    data-testid={`software-rule-delete-${r.id}`}
                  ><Trash2 className="h-3 w-3" /> Delete</button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function InventoryTable({ items }) {
  if (!items?.length) {
    return <EmptyState icon={Package} title="Software inventory empty" description="As agents report their software, discovered packages appear here." />;
  }
  return (
    <div className="rounded-2xl border border-border bg-card overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-background/60 border-b border-border">
          <tr className="text-left text-xs text-muted-foreground">
            <th className="px-4 py-3 font-medium">Name</th>
            <th className="px-3 py-3 font-medium">Publisher</th>
            <th className="px-3 py-3 font-medium">Category</th>
            <th className="px-3 py-3 font-medium">Versions</th>
            <th className="px-3 py-3 font-medium">Devices</th>
            <th className="px-3 py-3 font-medium">First seen</th>
            <th className="px-3 py-3 font-medium">Last seen</th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.key} className="border-t border-border hover:bg-foreground/[0.02]" data-testid={`software-inventory-row-${s.key}`}>
              <td className="px-4 py-2 font-medium">{s.name}</td>
              <td className="px-3 py-2 text-muted-foreground">{s.publisher || "—"}</td>
              <td className="px-3 py-2 text-muted-foreground">{s.category || "Uncategorized"}</td>
              <td className="px-3 py-2 text-muted-foreground text-xs font-mono truncate max-w-[220px]">{(s.versions || []).slice(0,3).join(", ") || "—"}</td>
              <td className="px-3 py-2 tabular-nums">{s.device_count || 0}</td>
              <td className="px-3 py-2 text-muted-foreground text-xs">{formatRelative(s.first_seen)}</td>
              <td className="px-3 py-2 text-muted-foreground text-xs">{formatRelative(s.last_seen)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function SoftwarePolicyPage() {
  const { user } = useAuth();
  const canAct = hasRole(user, "admin");
  const [policy, setPolicy] = useState(null);
  const [compliance, setCompliance] = useState(null);
  const [inventory, setInventory] = useState([]);
  const [rulesAllow, setRulesAllow] = useState([]);
  const [rulesBlock, setRulesBlock] = useState([]);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [tab, setTab] = useState("overview");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [p, c, i, ra, rb] = await Promise.all([
        api.get("/software/policy"),
        api.get("/software/compliance"),
        api.get(`/software/inventory?limit=500${q ? `&q=${encodeURIComponent(q)}` : ""}${category ? `&category=${encodeURIComponent(category)}` : ""}`),
        api.get("/software/rules?mode=allow"),
        api.get("/software/rules?mode=block"),
      ]);
      setPolicy(p.data); setCompliance(c.data); setInventory(i.data || []);
      setRulesAllow(ra.data || []); setRulesBlock(rb.data || []);
    } catch (e) { toast.error(extractError(e, "Failed to load")); }
    finally { setBusy(false); }
  }, [q, category]);

  useEffect(() => { load(); }, [load]);

  const setMode = async (mode) => {
    try {
      await api.put("/software/policy", { mode });
      toast.success(`Policy mode set to ${MODE_META[mode].label}`);
      load();
    } catch (e) { toast.error(extractError(e, "Failed to set mode")); }
  };

  const addRule = async (mode, payload) => {
    await api.post("/software/rules", { ...payload, mode });
    toast.success(`${mode === "allow" ? "Approved" : "Blocked"}: ${payload.name || payload.publisher}`);
    load();
  };
  const deleteRule = async (id) => {
    try { await api.delete(`/software/rules/${id}`); toast.success("Rule removed"); load(); }
    catch (e) { toast.error(extractError(e, "Failed to remove")); }
  };

  const modeKey = policy?.mode || "monitor";
  const modeMeta = MODE_META[modeKey];
  const ModeIcon = modeMeta?.icon || Shield;

  const categories = useMemo(() => {
    const set = new Set();
    inventory.forEach((s) => s.category && set.add(s.category));
    return Array.from(set).sort();
  }, [inventory]);

  return (
    <div className="space-y-6" data-testid="software-policy-page">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-2xl font-semibold tracking-tight">Software Policy & Compliance</div>
          <div className="mt-1 text-sm text-muted-foreground">
            Inventory every installed application, enforce approved/blocked lists, and track compliance across your fleet.
          </div>
        </div>
        <button onClick={load} className="h-10 w-10 rounded-lg border border-border hover:bg-foreground/5 flex items-center justify-center" data-testid="software-refresh">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        </button>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="rounded-2xl border border-border bg-card p-4 flex items-center gap-4" data-testid="software-kpi-compliance">
          <ScoreRing score={compliance?.compliance_score ?? 100} />
          <div className="min-w-0">
            <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Compliance Score</div>
            <div className="mt-1 text-xs text-muted-foreground">
              {compliance?.violating_devices || 0} devices with violations
            </div>
            <div className="text-[11px] text-muted-foreground mt-0.5">
              {compliance?.total_devices || 0} devices total
            </div>
          </div>
        </div>
        <div className="rounded-2xl border border-border bg-card p-4" data-testid="software-kpi-mode">
          <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Policy Mode</div>
          <div className="mt-1 flex items-center gap-2">
            <ModeIcon className="h-4 w-4 text-primary" />
            <span className="text-lg font-semibold">{modeMeta?.label || "—"}</span>
          </div>
          <div className="text-[11px] text-muted-foreground mt-1">{modeMeta?.desc}</div>
        </div>
        <div className="rounded-2xl border border-border bg-card p-4" data-testid="software-kpi-catalog">
          <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Software Catalog</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">{compliance?.catalog_total || 0}</div>
          <div className="text-[11px] text-muted-foreground">unique applications</div>
        </div>
        <div className="rounded-2xl border border-border bg-card p-4" data-testid="software-kpi-violations">
          <div className="text-[11px] uppercase tracking-widest text-muted-foreground">Active Violations</div>
          <div className="mt-1 text-2xl font-semibold tabular-nums text-red-300">{compliance?.active_violations || 0}</div>
          <div className="text-[11px] text-muted-foreground">requires review</div>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList data-testid="software-policy-tabs">
          <TabsTrigger value="overview" data-testid="software-tab-overview">Overview</TabsTrigger>
          <TabsTrigger value="inventory" data-testid="software-tab-inventory">Inventory</TabsTrigger>
          <TabsTrigger value="approved" data-testid="software-tab-approved">Approved</TabsTrigger>
          <TabsTrigger value="blocked" data-testid="software-tab-blocked">Blocked</TabsTrigger>
          <TabsTrigger value="policy" data-testid="software-tab-policy">Policy</TabsTrigger>
        </TabsList>

        {/* Overview */}
        <TabsContent value="overview" className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-2xl border border-border bg-card p-4">
            <div className="text-sm font-semibold mb-3 flex items-center gap-2"><Package className="h-4 w-4 text-primary" /> Most installed applications</div>
            {(compliance?.top_installed || []).length === 0 ? (
              <div className="text-sm text-muted-foreground py-6 text-center">No inventory yet.</div>
            ) : (
              <ul className="space-y-2">
                {compliance.top_installed.map((s) => (
                  <li key={`${s.name}|${s.publisher}`} className="flex items-center gap-3 text-sm">
                    <span className="h-6 w-6 rounded-md bg-foreground/[0.05] border border-border flex items-center justify-center"><Package className="h-3 w-3" /></span>
                    <div className="min-w-0 flex-1">
                      <div className="font-medium truncate">{s.name}</div>
                      <div className="text-[11px] text-muted-foreground truncate">{s.publisher || "—"} · {s.category || "Uncategorized"}</div>
                    </div>
                    <div className="text-xs text-muted-foreground tabular-nums">{s.device_count} devices</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="rounded-2xl border border-border bg-card p-4">
            <div className="text-sm font-semibold mb-3 flex items-center gap-2"><PackagePlus className="h-4 w-4 text-primary" /> Recently detected</div>
            {(compliance?.recently_detected || []).length === 0 ? (
              <div className="text-sm text-muted-foreground py-6 text-center">No inventory yet.</div>
            ) : (
              <ul className="space-y-2">
                {compliance.recently_detected.map((s) => (
                  <li key={`${s.name}|${s.publisher}`} className="flex items-center gap-3 text-sm">
                    <span className="h-6 w-6 rounded-md bg-foreground/[0.05] border border-border flex items-center justify-center"><PackagePlus className="h-3 w-3" /></span>
                    <div className="min-w-0 flex-1">
                      <div className="font-medium truncate">{s.name}</div>
                      <div className="text-[11px] text-muted-foreground truncate">{s.publisher || "—"} · {s.category || "Uncategorized"}</div>
                    </div>
                    <div className="text-xs text-muted-foreground">{formatRelative(s.first_seen)}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </TabsContent>

        {/* Inventory */}
        <TabsContent value="inventory" className="mt-4 space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative">
              <Search className="h-3.5 w-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search software or publisher…" className="h-10 w-72 pl-8" data-testid="software-inventory-search" />
            </div>
            <Select value={category || "all"} onValueChange={(v) => setCategory(v === "all" ? "" : v)}>
              <SelectTrigger className="h-10 w-[180px]" data-testid="software-inventory-category"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {categories.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <InventoryTable items={inventory} />
        </TabsContent>

        {/* Approved (allowlist) */}
        <TabsContent value="approved" className="mt-4 space-y-4">
          {canAct && (
            <div className="rounded-2xl border border-border bg-card p-4">
              <div className="text-sm font-semibold mb-3 flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-emerald-400" /> Add approved software</div>
              <RuleForm mode="allow" onSubmit={(p) => addRule("allow", p)} />
            </div>
          )}
          <RulesTable rules={rulesAllow} onDelete={deleteRule} canAct={canAct} mode="allow" />
        </TabsContent>

        {/* Blocked (blocklist) */}
        <TabsContent value="blocked" className="mt-4 space-y-4">
          {canAct && (
            <div className="rounded-2xl border border-border bg-card p-4">
              <div className="text-sm font-semibold mb-3 flex items-center gap-2"><Ban className="h-4 w-4 text-red-400" /> Add blocked software</div>
              <RuleForm mode="block" onSubmit={(p) => addRule("block", p)} />
            </div>
          )}
          <RulesTable rules={rulesBlock} onDelete={deleteRule} canAct={canAct} mode="block" />
        </TabsContent>

        {/* Policy mode */}
        <TabsContent value="policy" className="mt-4">
          <div className="rounded-2xl border border-border bg-card p-6">
            <div className="text-sm font-semibold mb-4 flex items-center gap-2"><Filter className="h-4 w-4 text-primary" /> Policy Mode</div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
              {Object.entries(MODE_META).map(([key, meta]) => {
                const Icon = meta.icon;
                const active = modeKey === key;
                return (
                  <button
                    key={key}
                    disabled={!canAct}
                    onClick={() => setMode(key)}
                    data-testid={`software-policy-mode-${key}`}
                    className={cn(
                      "text-left rounded-2xl border p-4 transition-colors",
                      active ? "border-primary/60 ring-2 ring-primary/40 bg-primary/[0.05]" : "border-border bg-foreground/[0.02] hover:bg-foreground/[0.04]",
                      !canAct && "opacity-70 cursor-not-allowed",
                    )}
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <Icon className="h-4 w-4 text-primary" />
                      <div className="font-semibold">{meta.label}</div>
                      {active && <StatBadge variant="healthy">Active</StatBadge>}
                    </div>
                    <div className="mt-2 text-xs text-muted-foreground">{meta.desc}</div>
                  </button>
                );
              })}
            </div>
            {!canAct && <div className="mt-4 text-xs text-muted-foreground">Only Admins can change the policy mode.</div>}
            <div className="mt-6 text-[11px] text-muted-foreground">
              Policy changes take effect on the next inventory refresh from each agent. Existing violation alerts will auto-resolve if the software no longer matches the new policy.
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
