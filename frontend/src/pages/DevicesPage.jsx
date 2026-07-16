import React, { useCallback, useEffect, useMemo, useState } from "react";
import { MonitorSmartphone, Search, Plus, LayoutGrid, Table as TableIcon, ChevronLeft, ChevronRight, ArrowUpDown, RefreshCw, X, Zap, Users2, Wrench, CheckSquare, Square, Download } from "lucide-react";
import { toast } from "sonner";
import { motion, AnimatePresence } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { DeviceCard } from "../components/DeviceCard";
import { EmptyState } from "../components/EmptyState";
import { OnlineBadge, RiskBadge, StatBadge } from "../components/StatBadge";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Button } from "../components/ui/button";
import { formatRelative, hasRole, extractError } from "../lib/format";
import { useAuth } from "../contexts/AuthContext";
import { useDashboardSocket } from "../contexts/WebSocketContext";
import DownloadInstallerDialog from "../components/EnrollDeviceDialog";
import RegisterComputerDialog from "../components/RegisterComputerDialog";
import BulkActionsDialog from "../components/BulkActionsDialog";
import { MaintenanceBadge } from "../components/MaintenanceDialog";

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];
const SORT_OPTIONS = [
  { key: "enrolled_at", label: "Registered" },
  { key: "hostname", label: "Hostname" },
  { key: "os", label: "OS" },
  { key: "last_seen", label: "Last seen" },
  { key: "health", label: "Health" },
  { key: "ram", label: "RAM" },
];

export default function DevicesPage() {
  const { user } = useAuth();
  const { subscribe } = useDashboardSocket();
  const navigate = useNavigate();

  const [payload, setPayload] = useState(null); // { items, total, page, page_size, total_pages }
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [status, setStatus] = useState("all");
  const [os, setOs] = useState("");
  const [sortBy, setSortBy] = useState("enrolled_at");
  const [sortDir, setSortDir] = useState("desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [view, setView] = useState("table");
  const [openEnroll, setOpenEnroll] = useState(false);
  const [openRegister, setOpenRegister] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  // Fleet management state
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [openBulk, setOpenBulk] = useState(false);
  const [groups, setGroups] = useState([]);
  const [groupFilter, setGroupFilter] = useState("");
  const [openAssignGroup, setOpenAssignGroup] = useState(false);

  // Debounce search input
  useEffect(() => {
    const id = setTimeout(() => setDebouncedQ(q.trim()), 300);
    return () => clearTimeout(id);
  }, [q]);

  useEffect(() => {
    setPage(1);
  }, [debouncedQ, status, os, sortBy, sortDir, pageSize]);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const params = new URLSearchParams();
      if (debouncedQ) params.set("q", debouncedQ);
      if (status !== "all") params.set("status", status);
      if (os.trim()) params.set("os", os.trim());
      params.set("sort_by", sortBy);
      params.set("sort_dir", sortDir);
      params.set("page", String(page));
      params.set("page_size", String(pageSize));
      const r = await api.get(`/devices?${params.toString()}`);
      setPayload(r.data);
    } catch (e) {
      toast.error(extractError(e, "Failed to load computers"));
    } finally {
      setRefreshing(false);
    }
  }, [debouncedQ, status, os, sortBy, sortDir, page, pageSize]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api.get("/device-groups").then(({ data }) => setGroups(data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    return subscribe((msg) => {
      if (["telemetry", "device.online", "device.offline", "inventory"].includes(msg.type)) {
        load();
      }
    });
  }, [subscribe, load]);

  const items = payload?.items || [];
  const filteredItems = useMemo(() => {
    if (!groupFilter) return items;
    return items.filter((d) => (d.group_ids || []).includes(groupFilter));
  }, [items, groupFilter]);
  const selectedDevices = useMemo(
    () => items.filter((d) => selectedIds.has(d.id)),
    [items, selectedIds],
  );
  const allVisibleSelected = filteredItems.length > 0 && filteredItems.every((d) => selectedIds.has(d.id));
  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const toggleSelectAllVisible = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) filteredItems.forEach((d) => next.delete(d.id));
      else filteredItems.forEach((d) => next.add(d.id));
      return next;
    });
  };
  const clearSelection = () => setSelectedIds(new Set());
  const assignToGroup = async (groupId) => {
    try {
      await api.post(`/device-groups/${groupId}/assign`, { device_ids: [...selectedIds] });
      toast.success(`Assigned ${selectedIds.size} device(s) to group`);
      load();
      setOpenAssignGroup(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Assignment failed");
    }
  };
  const total = payload?.total ?? 0;
  const totalPages = payload?.total_pages || 1;
  const hasAnyDevices = total > 0 || debouncedQ === "" && status === "all" && os === "";
  const isEmptyDb = payload && total === 0 && !debouncedQ && status === "all" && !os;

  const toggleSort = (key) => {
    if (sortBy === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(key);
      setSortDir("desc");
    }
  };

  const clearFilters = () => {
    setQ("");
    setStatus("all");
    setOs("");
    setSortBy("enrolled_at");
    setSortDir("desc");
  };

  const canManage = hasRole(user, "technician");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-2xl font-semibold tracking-tight">Computers</div>
          <div className="mt-1 text-sm text-muted-foreground">
            {payload
              ? `${total} computer${total === 1 ? "" : "s"} in ${user?.role === "owner" ? "your organization" : "your fleet"}`
              : "Loading\u2026"}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="hidden sm:flex items-center rounded-xl border border-border p-0.5">
            <button
              onClick={() => setView("grid")}
              className={`h-8 w-8 rounded-lg flex items-center justify-center ${view === "grid" ? "bg-foreground/10 text-foreground" : "text-muted-foreground"}`}
              data-testid="devices-view-grid"
              aria-label="Grid view"
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
            <button
              onClick={() => setView("table")}
              className={`h-8 w-8 rounded-lg flex items-center justify-center ${view === "table" ? "bg-foreground/10 text-foreground" : "text-muted-foreground"}`}
              data-testid="devices-view-table"
              aria-label="Table view"
            >
              <TableIcon className="h-4 w-4" />
            </button>
          </div>
          <Button variant="ghost" size="sm" onClick={load} disabled={refreshing} data-testid="devices-refresh">
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} /> Refresh
          </Button>
          {canManage && (
            <>
              <Button variant="secondary" onClick={() => setOpenRegister(true)} data-testid="devices-register-button">
                <Plus className="h-4 w-4" /> Register computer
              </Button>
              <Button onClick={() => setOpenEnroll(true)} data-testid="devices-enroll-button">
                <Download className="h-4 w-4" /> Download Agent
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="rounded-2xl border border-border bg-card p-3 sm:p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="relative flex-1 min-w-[220px] max-w-lg">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search hostname, IP, MAC, serial, OS, CPU…"
              className="pl-9 pr-9"
              data-testid="devices-search-input"
            />
            {q && (
              <button
                onClick={() => setQ("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 h-6 w-6 rounded-md hover:bg-foreground/10 flex items-center justify-center"
                aria-label="Clear search"
              >
                <X className="h-3 w-3 text-muted-foreground" />
              </button>
            )}
          </div>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="w-[160px]" data-testid="devices-filter-status">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="online">Online</SelectItem>
              <SelectItem value="offline">Offline</SelectItem>
              <SelectItem value="healthy">Healthy</SelectItem>
              <SelectItem value="warning">Warning</SelectItem>
              <SelectItem value="high_risk">High risk</SelectItem>
              <SelectItem value="critical">Critical</SelectItem>
              <SelectItem value="has_agent">With agent</SelectItem>
              <SelectItem value="no_agent">Without agent</SelectItem>
            </SelectContent>
          </Select>
          <Input
            value={os}
            onChange={(e) => setOs(e.target.value)}
            placeholder="OS filter (e.g. Windows)"
            className="w-[200px]"
            data-testid="devices-filter-os"
          />
          <Select value={groupFilter || "__all__"} onValueChange={(v) => setGroupFilter(v === "__all__" ? "" : v)}>
            <SelectTrigger className="w-[180px]" data-testid="devices-filter-group">
              <SelectValue placeholder="All groups" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">All groups</SelectItem>
              {groups.map((g) => (
                <SelectItem key={g.id} value={g.id}>{g.name} ({g.device_count})</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={sortBy} onValueChange={setSortBy}>
            <SelectTrigger className="w-[160px]" data-testid="devices-sort">
              <SelectValue placeholder="Sort" />
            </SelectTrigger>
            <SelectContent>
              {SORT_OPTIONS.map((s) => (
                <SelectItem key={s.key} value={s.key}>Sort by {s.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <button
            onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
            className="h-10 w-10 rounded-xl border border-border flex items-center justify-center hover:bg-foreground/5"
            title={`Sort direction: ${sortDir}`}
            data-testid="devices-sort-dir"
          >
            <ArrowUpDown className={`h-4 w-4 transition-transform ${sortDir === "asc" ? "" : "rotate-180"}`} />
          </button>
          {(debouncedQ || status !== "all" || os) && (
            <Button variant="ghost" size="sm" onClick={clearFilters}>Clear filters</Button>
          )}
        </div>
      </div>

      {/* Body */}
      {payload === null ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-[220px] rounded-2xl border border-border bg-card animate-pulse" />
          ))}
        </div>
      ) : isEmptyDb ? (
        <EmptyState
          icon={MonitorSmartphone}
          title="No computers yet"
          description="Register a computer manually to inventory it, or enroll an agent to receive live telemetry. You can also enroll an agent later to attach one to a manually-registered record."
          primaryLabel="Register a computer"
          primaryAction={canManage ? () => setOpenRegister(true) : undefined}
          secondary={
            canManage ? (
              <Button variant="secondary" onClick={() => setOpenEnroll(true)}>
                <Download className="h-4 w-4" /> Download installer
              </Button>
            ) : null
          }
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Search}
          title="No computers match your filters"
          description="Try clearing the search or changing filters."
          primaryLabel="Clear filters"
          primaryAction={clearFilters}
        />
      ) : view === "grid" ? (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
          {filteredItems.map((d) => (
            <div key={d.id} className="relative">
              <div className="absolute top-2 left-2 z-10">
                <input
                  type="checkbox"
                  checked={selectedIds.has(d.id)}
                  onChange={() => toggleSelect(d.id)}
                  onClick={(e) => e.stopPropagation()}
                  data-testid={`device-select-${d.id}`}
                  className="h-4 w-4 accent-primary"
                />
              </div>
              <MaintenanceBadge device={d} className="absolute top-2 right-2 z-10" />
              <DeviceCard device={d} />
            </div>
          ))}
        </motion.div>
      ) : (
        <div className="rounded-2xl border border-border bg-card overflow-hidden shadow-[var(--shadow-1)]">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="devices-table">
              <thead className="bg-background/60 border-b border-border sticky top-0 z-10">
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="px-3 py-3 w-8">
                    <button onClick={toggleSelectAllVisible} className="text-muted-foreground hover:text-foreground" data-testid="devices-select-all">
                      {allVisibleSelected ? <CheckSquare className="h-4 w-4" /> : <Square className="h-4 w-4" />}
                    </button>
                  </th>
                  <SortableTh label="Hostname" k="hostname" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} />
                  <th className="px-3 py-3 font-medium">Status</th>
                  <th className="px-3 py-3 font-medium">IP</th>
                  <th className="px-3 py-3 font-medium">MAC</th>
                  <SortableTh label="OS" k="os" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} />
                  <th className="px-3 py-3 font-medium">Serial</th>
                  <th className="px-3 py-3 font-medium">CPU</th>
                  <SortableTh label="RAM" k="ram" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} className="tabular-nums" />
                  <th className="px-3 py-3 font-medium tabular-nums">Disk</th>
                  <SortableTh label="Health" k="health" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} className="tabular-nums" />
                  <SortableTh label="Last seen" k="last_seen" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} />
                </tr>
              </thead>
              <tbody>
                {filteredItems.map((d) => (
                  <tr
                    key={d.id}
                    onClick={() => navigate(`/app/devices/${d.id}`)}
                    className={`cursor-pointer hover:bg-foreground/[0.03] border-t border-border ${selectedIds.has(d.id) ? "bg-primary/5" : ""}`}
                    data-testid="devices-table-row"
                  >
                    <td className="px-3 py-3 w-8" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(d.id)}
                        onChange={() => toggleSelect(d.id)}
                        data-testid={`device-select-${d.id}`}
                        className="h-4 w-4 accent-primary"
                      />
                    </td>
                    <td className="px-4 py-3 min-w-[200px]">
                      <div className="font-medium truncate max-w-[240px]">{d.display_name || d.hostname}</div>
                      <div className="text-xs text-muted-foreground truncate max-w-[240px] flex items-center gap-1">
                        {d.hostname}
                        {d.created_via === "manual" && (
                          <StatBadge variant="info" className="ml-1 !py-0 !px-1.5 !text-[9px]">manual</StatBadge>
                        )}
                        {d.has_agent && (
                          <StatBadge variant="healthy" className="ml-1 !py-0 !px-1.5 !text-[9px]">agent</StatBadge>
                        )}
                        <MaintenanceBadge device={d} className="!py-0 !px-1.5 !text-[9px]" />
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex flex-col gap-1">
                        <OnlineBadge online={d.is_online} />
                        {d.is_online && <RiskBadge risk={d.risk_level} />}
                      </div>
                    </td>
                    <td className="px-3 py-3 font-mono text-xs">{d.ip_address || <span className="text-muted-foreground">—</span>}</td>
                    <td className="px-3 py-3 font-mono text-xs">{d.mac_address || <span className="text-muted-foreground">—</span>}</td>
                    <td className="px-3 py-3">
                      <div className="truncate max-w-[140px]">{d.os_name || <span className="text-muted-foreground">—</span>}</div>
                      {d.os_version && <div className="text-xs text-muted-foreground truncate">{d.os_version}</div>}
                    </td>
                    <td className="px-3 py-3 font-mono text-xs truncate max-w-[140px]">{d.serial_number || <span className="text-muted-foreground">—</span>}</td>
                    <td className="px-3 py-3 truncate max-w-[180px]">{d.cpu || <span className="text-muted-foreground">—</span>}</td>
                    <td className="px-3 py-3 tabular-nums whitespace-nowrap">{d.ram_gb != null ? `${d.ram_gb} GB` : <span className="text-muted-foreground">—</span>}</td>
                    <td className="px-3 py-3 tabular-nums whitespace-nowrap">{d.disk_gb != null ? `${Math.round(d.disk_gb)} GB` : <span className="text-muted-foreground">—</span>}</td>
                    <td className="px-3 py-3 tabular-nums">{d.health_score ?? <span className="text-muted-foreground">—</span>}</td>
                    <td className="px-3 py-3 text-muted-foreground whitespace-nowrap">{formatRelative(d.last_seen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Pagination */}
      {payload && total > 0 && (
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="text-xs text-muted-foreground">
            Showing <span className="tabular-nums font-medium text-foreground">{Math.min((page - 1) * pageSize + 1, total)}</span>
            {" - "}
            <span className="tabular-nums font-medium text-foreground">{Math.min(page * pageSize, total)}</span>
            {" of "}
            <span className="tabular-nums font-medium text-foreground">{total}</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Select value={String(pageSize)} onValueChange={(v) => setPageSize(Number(v))}>
              <SelectTrigger className="w-[120px]" data-testid="devices-page-size">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_SIZE_OPTIONS.map((n) => (
                  <SelectItem key={n} value={String(n)}>{n} / page</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="h-9 w-9 rounded-lg border border-border hover:bg-foreground/5 disabled:opacity-40 flex items-center justify-center"
                data-testid="devices-page-prev"
                aria-label="Previous page"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <div className="text-xs text-muted-foreground tabular-nums px-2" data-testid="devices-page-indicator">
                Page {page} of {totalPages}
              </div>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="h-9 w-9 rounded-lg border border-border hover:bg-foreground/5 disabled:opacity-40 flex items-center justify-center"
                data-testid="devices-page-next"
                aria-label="Next page"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      <DownloadInstallerDialog
        open={openEnroll}
        onOpenChange={setOpenEnroll}
      />
      <RegisterComputerDialog
        open={openRegister}
        onOpenChange={setOpenRegister}
        onRegistered={(dev) => {
          load();
          toast.success(`Registered ${dev.hostname}`);
        }}
      />

      {/* Floating bulk actions bar */}
      <AnimatePresence>
        {selectedIds.size > 0 && (
          <motion.div
            initial={{ y: 100, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 100, opacity: 0 }}
            className="fixed left-1/2 -translate-x-1/2 bottom-6 z-40"
            data-testid="bulk-actions-bar"
          >
            <div className="rounded-2xl border border-border bg-card shadow-xl px-4 py-3 flex items-center gap-3 min-w-[420px]">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-lg bg-primary/15 text-primary flex items-center justify-center font-semibold text-sm">
                  {selectedIds.size}
                </div>
                <div className="text-sm">
                  <div className="font-medium">device{selectedIds.size !== 1 ? "s" : ""} selected</div>
                  <button onClick={clearSelection} className="text-[11px] text-muted-foreground hover:text-foreground">Clear</button>
                </div>
              </div>
              <div className="ml-auto flex items-center gap-2">
                {groups.length > 0 && (
                  <Button variant="outline" size="sm" onClick={() => setOpenAssignGroup(true)} data-testid="bulk-assign-group-btn">
                    <Users2 className="h-4 w-4 mr-1" /> Assign to group
                  </Button>
                )}
                <Button size="sm" onClick={() => setOpenBulk(true)} data-testid="open-bulk-actions-btn">
                  <Zap className="h-4 w-4 mr-1" /> Bulk actions
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <BulkActionsDialog
        open={openBulk}
        onOpenChange={(v) => { setOpenBulk(v); if (!v) load(); }}
        selectedDevices={selectedDevices}
        canAdmin={hasRole(user, "admin")}
        onDone={() => {}}
      />

      {/* Assign to Group dialog (inline lightweight) */}
      {openAssignGroup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={() => setOpenAssignGroup(false)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <div onClick={(e) => e.stopPropagation()} className="relative rounded-2xl border border-border bg-card p-6 w-full max-w-md">
            <div className="text-lg font-semibold mb-2">Assign {selectedIds.size} device(s) to a group</div>
            <div className="text-xs text-muted-foreground mb-4">A device can belong to multiple groups.</div>
            <div className="grid grid-cols-1 gap-2 max-h-72 overflow-auto">
              {groups.map((g) => (
                <button key={g.id} onClick={() => assignToGroup(g.id)}
                  className="text-left rounded-lg border border-border p-3 hover:border-primary/60 hover:bg-primary/5"
                  data-testid={`assign-to-${g.id}`}>
                  <div className="font-medium">{g.name}</div>
                  <div className="text-xs text-muted-foreground">{g.device_count} device(s)</div>
                </button>
              ))}
              {groups.length === 0 && (
                <div className="text-sm text-muted-foreground text-center py-4">
                  No groups yet. Create some from the Device Groups page.
                </div>
              )}
            </div>
            <div className="mt-4 flex justify-end">
              <Button variant="secondary" onClick={() => setOpenAssignGroup(false)}>Close</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SortableTh({ label, k, sortBy, sortDir, onSort, className = "" }) {
  const active = sortBy === k;
  return (
    <th className={`px-4 py-3 font-medium ${className}`}>
      <button
        onClick={() => onSort(k)}
        className={`inline-flex items-center gap-1 hover:text-foreground transition-colors ${active ? "text-foreground" : "text-muted-foreground"}`}
        data-testid={`sort-${k}`}
      >
        {label}
        <ArrowUpDown className={`h-3 w-3 opacity-60 ${active ? (sortDir === "asc" ? "" : "rotate-180") : ""}`} />
      </button>
    </th>
  );
}
