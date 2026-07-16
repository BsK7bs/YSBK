import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, Trash2, Plus, Copy, Check, KeyRound, Loader2, Info } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { extractError, formatRelative } from "../lib/format";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Switch } from "./ui/switch";

/**
 * Pairing codes UI \u2014 the universal-installer first-launch flow.
 *
 * Admins create short human-friendly codes (e.g. A7K2-9FQX-M3R8) that the end
 * user types into the agent's first-run window. Backend URL is baked into
 * the agent binary; no per-tenant installer customisation required.
 */
export default function PairingCodesTab() {
  const [codes, setCodes] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const [freshCodes, setFreshCodes] = useState({});
  const [creating, setCreating] = useState(false);
  const [label, setLabel] = useState("");
  const [singleUse, setSingleUse] = useState(false);
  const [maxUses, setMaxUses] = useState(50);
  const [ttlHours, setTtlHours] = useState(24);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await api.get("/pairing/codes");
      setCodes(r.data || []);
    } catch (e) {
      toast.error(extractError(e, "Failed to load pairing codes"));
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!label.trim()) { toast.error("Label required"); return; }
    setCreating(true);
    try {
      const r = await api.post("/pairing/codes", {
        label: label.trim(),
        single_use: singleUse,
        max_uses: singleUse ? 1 : Math.max(1, Math.min(100000, Number(maxUses) || 1)),
        ttl_hours: Math.max(1, Math.min(24 * 90, Number(ttlHours) || 24)),
      });
      setFreshCodes((cur) => ({ ...cur, [r.data.id]: r.data.code }));
      setLabel(""); setSingleUse(false); setMaxUses(50); setTtlHours(24);
      toast.success(`Pairing code '${r.data.label}' created`);
      await load();
    } catch (e) {
      toast.error(extractError(e, "Create failed"));
    } finally { setCreating(false); }
  };

  const revoke = async (id) => {
    if (!window.confirm("Revoke this pairing code? Already-paired devices are unaffected.")) return;
    try {
      await api.delete(`/pairing/codes/${id}`);
      toast.success("Code revoked");
      setFreshCodes((cur) => { const n = { ...cur }; delete n[id]; return n; });
      await load();
    } catch (e) { toast.error(extractError(e, "Revoke failed")); }
  };

  return (
    <div className="space-y-4" data-testid="pairing-codes-tab">
      <div className="rounded-md border border-blue-500/30 bg-blue-500/5 p-3 text-xs flex gap-2">
        <Info className="h-4 w-4 text-blue-500 flex-shrink-0 mt-0.5" />
        <div className="text-muted-foreground">
          <span className="font-medium text-blue-500">Universal installer flow.</span>{" "}
          The agent installer is the same for every organization. After install, the endpoint user is
          shown a first-run window that asks only for this pairing code \u2014 nothing else. No JSON, no
          backend URL, no technical settings.
        </div>
      </div>

      {/* Create form */}
      <div className="rounded-lg border border-border p-4 space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <KeyRound className="h-4 w-4 text-primary" /> Create pairing code
        </div>
        <div className="grid sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label>Label</Label>
            <Input value={label} onChange={(e) => setLabel(e.target.value)}
                   placeholder="e.g. Room 101 batch" data-testid="pairing-label" maxLength={80} />
          </div>
          <div className="space-y-1">
            <Label>Lifetime (hours)</Label>
            <Input type="number" min={1} max={24 * 90} value={ttlHours}
                   onChange={(e) => setTtlHours(e.target.value)} data-testid="pairing-ttl" />
          </div>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm">Single-use</div>
            <div className="text-[11px] text-muted-foreground">Auto-revokes after first pairing.</div>
          </div>
          <Switch checked={singleUse} onCheckedChange={setSingleUse} data-testid="pairing-single-use" />
        </div>
        {!singleUse && (
          <div className="space-y-1">
            <Label>Max devices</Label>
            <Input type="number" min={1} max={100000} value={maxUses}
                   onChange={(e) => setMaxUses(e.target.value)} data-testid="pairing-max-uses" />
          </div>
        )}
        <Button onClick={create} disabled={creating || !label.trim()} data-testid="pairing-create">
          {creating ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
          Generate code
        </Button>
      </div>

      {/* List */}
      <div className="flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          Active pairing codes. Each code is shown once at creation \u2014 copy it before closing.
        </div>
        <Button size="sm" variant="ghost" onClick={load} disabled={refreshing}>
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
        </Button>
      </div>
      {codes.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          No pairing codes yet.
        </div>
      ) : (
        <div className="space-y-2" data-testid="pairing-list">
          {codes.map((c) => (
            <PairingRow key={c.id} row={c} cleartext={freshCodes[c.id]} onRevoke={() => revoke(c.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function PairingRow({ row, cleartext, onRevoke }) {
  const [copied, setCopied] = useState(false);
  const copy = async (t) => {
    try { await navigator.clipboard.writeText(t); setCopied(true); setTimeout(() => setCopied(false), 1600); }
    catch { toast.error("Copy failed"); }
  };
  const expired = new Date(row.expires_at).getTime() < Date.now();
  return (
    <div className="rounded-lg border border-border p-3" data-testid={`pairing-row-${row.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <div className="text-sm font-semibold truncate">{row.label}</div>
            {row.single_use && <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary uppercase">Single-use</span>}
            {expired && <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-500 uppercase">Expired</span>}
          </div>
          <div className="mt-1 font-mono text-lg tracking-widest">{cleartext || row.code_masked}</div>
          <div className="text-[11px] text-muted-foreground mt-1">
            {row.use_count}/{row.max_uses} used \u00b7 expires {formatRelative(row.expires_at)}
          </div>
        </div>
        <div className="flex items-center gap-1">
          {cleartext && (
            <Button size="sm" variant="ghost" onClick={() => copy(cleartext)} title="Copy code">
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={onRevoke} title="Revoke">
            <Trash2 className="h-3.5 w-3.5 text-red-500" />
          </Button>
        </div>
      </div>
      {cleartext && (
        <div className="mt-2 text-[11px] text-emerald-500/80">
          Copy this code now \u2014 the full code is only shown at creation. Users type it into the agent's first-run window.
        </div>
      )}
    </div>
  );
}
