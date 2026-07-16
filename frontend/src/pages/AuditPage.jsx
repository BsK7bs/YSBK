import React, { useEffect, useState } from "react";
import { ScrollText } from "lucide-react";
import { api } from "../lib/api";
import { EmptyState } from "../components/EmptyState";
import { formatRelative } from "../lib/format";

export default function AuditPage() {
  const [events, setEvents] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get("/audit?limit=500")
      .then((r) => setEvents(r.data || []))
      .catch((e) => setError(e?.response?.status === 403 ? "forbidden" : "error"));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold tracking-tight">Audit Log</div>
        <div className="mt-1 text-sm text-muted-foreground">Chronological record of security-relevant events in your organization.</div>
      </div>

      {error === "forbidden" ? (
        <EmptyState icon={ScrollText} title="Admin access required" description="Only Admins and Owners can view the audit log." />
      ) : events === null ? (
        <div className="h-40 rounded-2xl border border-border bg-card animate-pulse" />
      ) : events.length === 0 ? (
        <EmptyState icon={ScrollText} title="No audit events yet" description="Every login, invite, enrollment, and remote action will be recorded here." />
      ) : (
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-background/60 border-b border-border">
              <tr className="text-left text-xs text-muted-foreground">
                <th className="px-4 py-3 font-medium">When</th>
                <th className="px-3 py-3 font-medium">Actor</th>
                <th className="px-3 py-3 font-medium">Event</th>
                <th className="px-3 py-3 font-medium">Target</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-t border-border">
                  <td className="px-4 py-2 text-muted-foreground whitespace-nowrap">{formatRelative(e.ts)}</td>
                  <td className="px-3 py-2">{e.actor_email || "system"}</td>
                  <td className="px-3 py-2 font-medium">{e.kind}</td>
                  <td className="px-3 py-2 text-muted-foreground truncate max-w-[240px]">{e.target || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
