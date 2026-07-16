import React, { useEffect, useState } from "react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "./ui/command";
import {
  LayoutDashboard,
  MonitorSmartphone,
  BellRing,
  Users,
  Settings,
  User as UserIcon,
  ScrollText,
} from "lucide-react";
import { api } from "../lib/api";

const NAV = [
  { label: "Dashboard", to: "/app/dashboard", icon: LayoutDashboard },
  { label: "Devices", to: "/app/devices", icon: MonitorSmartphone },
  { label: "Alerts", to: "/app/alerts", icon: BellRing },
  { label: "Team", to: "/app/team", icon: Users },
  { label: "Organization Settings", to: "/app/settings/organization", icon: Settings },
  { label: "My Profile", to: "/app/settings/profile", icon: UserIcon },
  { label: "Audit Log", to: "/app/audit", icon: ScrollText },
];

export default function CommandPalette({ open, onOpenChange, onNavigate }) {
  const [devices, setDevices] = useState([]);

  useEffect(() => {
    if (!open) return;
    api
      .get("/devices?page=1&page_size=100")
      .then((r) => setDevices(r.data?.items || []))
      .catch(() => setDevices([]));
  }, [open]);

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title="Command Palette" description="Search commands, devices, and pages">
      <CommandInput placeholder="Search commands, devices, pages…" data-testid="command-palette-input" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Navigate">
          {NAV.map((item) => (
            <CommandItem
              key={item.to}
              onSelect={() => {
                onNavigate(item.to);
                onOpenChange(false);
              }}
              data-testid={`command-palette-item-${item.to.replace(/\//g, "-")}`}
            >
              <item.icon className="h-4 w-4 mr-2" />
              {item.label}
            </CommandItem>
          ))}
        </CommandGroup>
        {devices.length > 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Devices">
              {devices.slice(0, 8).map((d) => (
                <CommandItem
                  key={d.id}
                  onSelect={() => {
                    onNavigate(`/app/devices/${d.id}`);
                    onOpenChange(false);
                  }}
                >
                  <MonitorSmartphone className="h-4 w-4 mr-2" />
                  <span className="truncate">{d.display_name || d.hostname}</span>
                  <span className="ml-auto text-[10px] text-muted-foreground uppercase">
                    {d.is_online ? "online" : "offline"}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  );
}
