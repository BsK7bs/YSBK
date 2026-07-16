import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  MonitorSmartphone,
  BellRing,
  Users,
  Settings,
  ScrollText,
  ChevronsLeft,
  ChevronsRight,
  X,
  ShieldCheck,
  Cpu,
  Package,
  Users2,
  Terminal,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { useDashboardSocket } from "../contexts/WebSocketContext";
import { hasRole } from "../lib/format";
import { cn } from "../lib/utils";

const PRIMARY = [
  { to: "/app/dashboard", label: "Dashboard", icon: LayoutDashboard, testId: "nav-dashboard" },
  { to: "/app/devices", label: "Devices", icon: MonitorSmartphone, testId: "nav-devices" },
  { to: "/app/groups", label: "Device Groups", icon: Users2, testId: "nav-groups" },
  { to: "/app/alerts", label: "Alerts", icon: BellRing, testId: "nav-alerts" },
  { to: "/app/commands", label: "Command History", icon: Terminal, testId: "nav-commands" },
  { to: "/app/software", label: "Software Policy", icon: Package, testId: "nav-software" },
  { to: "/app/team", label: "Team", icon: Users, testId: "nav-team" },
];

const SECONDARY = [
  { to: "/app/settings/organization", label: "Org Settings", icon: Settings, testId: "nav-org-settings" },
  { to: "/app/audit", label: "Audit Log", icon: ScrollText, adminOnly: true, testId: "nav-audit" },
];

function NavItem({ to, icon: Icon, label, collapsed, testId }) {
  return (
    <NavLink
      to={to}
      data-testid={testId}
      className={({ isActive }) =>
        cn(
          "group relative flex items-center gap-3 rounded-xl h-10 px-3 text-sm font-medium",
          "text-muted-foreground hover:text-foreground hover:bg-foreground/5 transition-colors",
          isActive && "text-foreground bg-foreground/[0.06] border border-border",
        )
      }
    >
      <Icon className="h-4 w-4 shrink-0" />
      {!collapsed && <span className="truncate">{label}</span>}
    </NavLink>
  );
}

function SidebarContent({ collapsed, onToggleCollapsed, onMobileClose, isMobile }) {
  const { user, organization, logout } = useAuth();
  const { status } = useDashboardSocket();
  const navigate = useNavigate();

  const wsColor =
    status === "connected" ? "bg-emerald-500" : status === "connecting" ? "bg-amber-500" : "bg-slate-500";

  return (
    <div
      className={cn(
        "h-full flex flex-col surface border-r border-border",
        collapsed ? "w-[76px]" : "w-[272px]",
        isMobile && "w-[280px]",
      )}
    >
      {/* Brand + collapse */}
      <div className="h-14 shrink-0 flex items-center gap-3 px-4 border-b border-border">
        <div className="h-9 w-9 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center">
          <Cpu className="h-4 w-4 text-primary" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <div className="text-sm font-semibold truncate" data-testid="sidebar-org-name">
              {organization?.name || "Digital Twin"}
            </div>
            <div className="text-[11px] text-muted-foreground truncate">Digital Twin Platform</div>
          </div>
        )}
        {isMobile ? (
          <button
            onClick={onMobileClose}
            data-testid="sidebar-close-mobile"
            className="ml-auto h-8 w-8 rounded-lg hover:bg-foreground/5 flex items-center justify-center"
          >
            <X className="h-4 w-4" />
          </button>
        ) : (
          <button
            onClick={onToggleCollapsed}
            data-testid="sidebar-toggle-collapse"
            className="ml-auto h-8 w-8 rounded-lg hover:bg-foreground/5 flex items-center justify-center hidden lg:flex"
            aria-label="Toggle sidebar"
          >
            {collapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
          </button>
        )}
      </div>

      {/* Primary nav */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {!collapsed && (
          <div className="px-2 pb-2 text-[10px] uppercase tracking-widest text-muted-foreground/70 font-semibold">
            Overview
          </div>
        )}
        {PRIMARY.map((item) => (
          <NavItem key={item.to} {...item} collapsed={collapsed} />
        ))}

        <div className={cn("pt-6", !collapsed && "px-2 pb-2 text-[10px] uppercase tracking-widest text-muted-foreground/70 font-semibold")}>{!collapsed && "Manage"}</div>
        {SECONDARY.filter((i) => !i.adminOnly || hasRole(user, "admin")).map((item) => (
          <NavItem key={item.to} {...item} collapsed={collapsed} />
        ))}
      </div>

      {/* Footer */}
      <div className="border-t border-border px-3 py-3 space-y-2">
        <div className={cn("flex items-center gap-2 px-2 text-xs", collapsed && "justify-center")}>
          <span className={cn("h-2 w-2 rounded-full", wsColor)} aria-hidden />
          {!collapsed && (
            <span className="text-muted-foreground" data-testid="ws-status">
              Live: {status}
            </span>
          )}
        </div>
        <button
          onClick={() => navigate("/app/settings/profile")}
          data-testid="sidebar-profile-button"
          className={cn(
            "w-full flex items-center gap-3 rounded-xl h-11 px-2 hover:bg-foreground/5 transition-colors",
            collapsed && "justify-center",
          )}
        >
          <div className="h-8 w-8 rounded-full bg-gradient-to-br from-primary/40 to-cyan-500/40 flex items-center justify-center text-xs font-semibold">
            {(user?.full_name || user?.email || "?").charAt(0).toUpperCase()}
          </div>
          {!collapsed && (
            <div className="min-w-0 text-left">
              <div className="text-sm font-medium truncate">{user?.full_name}</div>
              <div className="text-[11px] text-muted-foreground truncate flex items-center gap-1">
                <ShieldCheck className="h-3 w-3" /> {user?.role}
              </div>
            </div>
          )}
        </button>
        {!collapsed && (
          <button
            onClick={logout}
            data-testid="sidebar-logout-button"
            className="w-full text-xs text-muted-foreground hover:text-foreground text-left px-2 py-1"
          >
            Sign out
          </button>
        )}
      </div>
    </div>
  );
}

export default function Sidebar({ collapsed, onToggleCollapsed, mobileOpen, onMobileClose }) {
  return (
    <>
      {/* Desktop */}
      <aside className="hidden lg:block shrink-0">
        <div className="sticky top-0 h-screen">
          <SidebarContent collapsed={collapsed} onToggleCollapsed={onToggleCollapsed} />
        </div>
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onMobileClose} />
          <div className="absolute inset-y-0 left-0">
            <SidebarContent collapsed={false} onMobileClose={onMobileClose} isMobile />
          </div>
        </div>
      )}
    </>
  );
}
