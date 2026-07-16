import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { motion } from "framer-motion";
import {
  Plus, Trash2, Pencil, Users2, School, Server, Building2, BookOpen, Cpu, HardDrive,
  Loader2, ChevronRight, X, Save,
} from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../contexts/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "../components/ui/dialog";
import { StatBadge } from "../components/StatBadge";
import { EmptyState } from "../components/EmptyState";
import { hasRole } from "../lib/format";

const COLORS = [
  { name: "blue",    ring: "border-blue-500/40 bg-blue-500/10 text-blue-300" },
  { name: "emerald", ring: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" },
  { name: "amber",   ring: "border-amber-500/40 bg-amber-500/10 text-amber-300" },
  { name: "purple",  ring: "border-purple-500/40 bg-purple-500/10 text-purple-300" },
  { name: "pink",    ring: "border-pink-500/40 bg-pink-500/10 text-pink-300" },
  { name: "cyan",    ring: "border-cyan-500/40 bg-cyan-500/10 text-cyan-300" },
  { name: "red",     ring: "border-red-500/40 bg-red-500/10 text-red-300" },
];
const ICONS = { school: School, server: Server, building: Building2, library: BookOpen, cpu: Cpu, hdd: HardDrive, users: Users2 };
const iconOf = (k) => ICONS[k] || Users2;
const colorOf = (c) => COLORS.find((x) => x.name === c) || COLORS[0];

export default function DeviceGroupsPage() {
  const { user } = useAuth();
  const canAdmin = hasRole(user, "admin");
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // {create:true} | group | null
  const [devices, setDevices] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/device-groups");
      setGroups(data);
    } catch (e) {
      toast.error("Failed to load groups");
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const del = async (group) => {
    if (!window.confirm(`Delete group "${group.name}"? Devices remain, only the label is removed.`)) return;
    try {
      await api.delete(`/device-groups/${group.id}`);
      toast.success("Group deleted");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Delete failed");
    }
  };

  const openDevices = async (group) => {
    try {
      const { data } = await api.get(`/device-groups/${group.id}/devices`);
      setDevices({ group, list: data });
    } catch { toast.error("Failed to load devices"); }
  };

  return (
    <div className="space-y-4" data-testid="device-groups-page">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-2xl font-semibold tracking-tight">Device Groups</div>
          <div className="text-sm text-muted-foreground">Organize computers by lab, room, department, or purpose. Bulk actions can target a whole group.</div>
        </div>
        {canAdmin && (
          <Button onClick={() => setEditing({ create: true, color: "blue", icon: "users" })} data-testid="create-group-btn">
            <Plus className="h-4 w-4 mr-1" /> New group
          </Button>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : groups.length === 0 ? (
        <EmptyState
          icon={Users2}
          title="No groups yet"
          description="Create groups like 'Lab A', 'Library', 'Servers' to organize your fleet."
          action={canAdmin ? { label: "Create first group", onClick: () => setEditing({ create: true, color: "blue", icon: "users" }) } : null}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {groups.map((g) => {
            const Icon = iconOf(g.icon);
            const color = colorOf(g.color);
            return (
              <motion.div key={g.id} layout
                className="rounded-2xl border border-border bg-card p-4 hover:border-primary/40 transition"
                data-testid={`group-card-${g.id}`}>
                <div className="flex items-start gap-3">
                  <div className={`h-10 w-10 rounded-xl border ${color.ring} flex items-center justify-center`}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold truncate">{g.name}</div>
                    {g.description && <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{g.description}</div>}
                    <div className="mt-2 flex items-center gap-2">
                      <StatBadge variant="info">{g.device_count} device{g.device_count !== 1 ? "s" : ""}</StatBadge>
                    </div>
                  </div>
                </div>
                <div className="mt-3 flex items-center gap-2 justify-end">
                  <Button variant="outline" size="sm" onClick={() => openDevices(g)}>View devices <ChevronRight className="h-3 w-3 ml-1" /></Button>
                  {canAdmin && (
                    <>
                      <Button variant="outline" size="sm" onClick={() => setEditing({ ...g })}><Pencil className="h-3 w-3" /></Button>
                      <Button variant="outline" size="sm" onClick={() => del(g)} className="text-red-400 hover:text-red-500"><Trash2 className="h-3 w-3" /></Button>
                    </>
                  )}
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      <GroupEditor open={!!editing} initial={editing} onOpenChange={(v) => !v && setEditing(null)} onSaved={load} />

      <Dialog open={!!devices} onOpenChange={(v) => !v && setDevices(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{devices?.group?.name}</DialogTitle>
            <DialogDescription>{devices?.list?.length || 0} devices</DialogDescription>
          </DialogHeader>
          <div className="max-h-96 overflow-auto">
            {(devices?.list || []).length === 0 ? (
              <div className="text-sm text-muted-foreground text-center py-6">No devices assigned yet.</div>
            ) : (
              (devices?.list || []).map((d) => (
                <div key={d.id} className="flex items-center gap-2 py-1.5 border-b border-border last:border-b-0">
                  <div className={`h-2 w-2 rounded-full ${d.is_online ? "bg-emerald-500" : "bg-slate-500"}`} />
                  <div className="flex-1 truncate text-sm">{d.display_name || d.hostname}</div>
                  <div className="text-xs text-muted-foreground">{d.os_name}</div>
                </div>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function GroupEditor({ open, initial, onOpenChange, onSaved }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor] = useState("blue");
  const [icon, setIcon] = useState("users");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(initial?.name || ""); setDescription(initial?.description || "");
    setColor(initial?.color || "blue"); setIcon(initial?.icon || "users");
  }, [open, initial]);

  const save = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      if (initial?.create) {
        await api.post("/device-groups", { name, description, color, icon });
        toast.success("Group created");
      } else {
        await api.patch(`/device-groups/${initial.id}`, { name, description, color, icon });
        toast.success("Group updated");
      }
      onSaved?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="group-editor-dialog">
        <DialogHeader>
          <DialogTitle>{initial?.create ? "Create device group" : "Edit group"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Name</div>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Computer Lab A" data-testid="group-name-input" />
          </div>
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Description</div>
            <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional description" />
          </div>
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Color</div>
            <div className="flex gap-2">
              {COLORS.map((c) => (
                <button key={c.name} onClick={() => setColor(c.name)}
                  className={`h-8 w-8 rounded-lg border-2 ${color === c.name ? "border-foreground" : "border-transparent"} ${c.ring}`}
                  title={c.name} />
              ))}
            </div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Icon</div>
            <div className="flex gap-2 flex-wrap">
              {Object.entries(ICONS).map(([k, Icon]) => (
                <button key={k} onClick={() => setIcon(k)}
                  className={`h-8 w-8 rounded-lg border ${icon === k ? "border-primary text-primary" : "border-border text-muted-foreground"} flex items-center justify-center hover:border-primary/60`}>
                  <Icon className="h-4 w-4" />
                </button>
              ))}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={saving || !name.trim()} data-testid="group-save-btn">
            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
            {initial?.create ? "Create" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
