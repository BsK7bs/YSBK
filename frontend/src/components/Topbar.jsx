import React, { useMemo } from "react";
import { useLocation, useNavigate, Link } from "react-router-dom";
import { Menu, Search, Sun, Moon } from "lucide-react";
import { useTheme } from "../contexts/ThemeContext";
import { useAuth } from "../contexts/AuthContext";
import { useDashboardSocket } from "../contexts/WebSocketContext";
import { cn } from "../lib/utils";
import { NotificationCenter } from "./NotificationCenter";

const LABELS = {
  dashboard: "Dashboard",
  devices: "Devices",
  alerts: "Alerts",
  team: "Team",
  settings: "Settings",
  organization: "Organization",
  profile: "Profile",
  audit: "Audit Log",
  app: "Home",
};

export default function Topbar({ onOpenMobileSidebar, onOpenPalette }) {
  const { theme, toggle } = useTheme();
  const { user } = useAuth();
  const { status } = useDashboardSocket();
  const location = useLocation();
  const navigate = useNavigate();

  const crumbs = useMemo(() => {
    const parts = location.pathname.split("/").filter(Boolean);
    return parts.map((p, idx) => ({
      label: LABELS[p] || p.replace(/-/g, " "),
      href: "/" + parts.slice(0, idx + 1).join("/"),
    }));
  }, [location.pathname]);

  return (
    <header
      data-testid="topbar"
      className={cn(
        "sticky top-0 z-30 h-14 flex items-center gap-3 px-4 sm:px-6",
        "border-b border-border bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60",
      )}
    >
      <button
        onClick={onOpenMobileSidebar}
        data-testid="topbar-mobile-menu"
        className="lg:hidden h-9 w-9 rounded-lg hover:bg-foreground/5 flex items-center justify-center"
      >
        <Menu className="h-4 w-4" />
      </button>

      {/* Breadcrumbs */}
      <nav className="hidden md:flex items-center gap-2 text-sm text-muted-foreground min-w-0">
        {crumbs.map((c, i) => (
          <React.Fragment key={c.href}>
            {i > 0 && <span className="opacity-40">/</span>}
            <Link
              to={c.href}
              className={cn(
                "truncate capitalize hover:text-foreground transition-colors",
                i === crumbs.length - 1 && "text-foreground font-medium",
              )}
            >
              {c.label}
            </Link>
          </React.Fragment>
        ))}
      </nav>

      <div className="flex-1" />

      {/* Search / palette */}
      <button
        onClick={onOpenPalette}
        data-testid="topbar-open-palette"
        className={cn(
          "hidden sm:inline-flex items-center gap-2 h-9 px-3 rounded-lg",
          "bg-foreground/[0.03] border border-border text-muted-foreground text-sm",
          "hover:bg-foreground/[0.05] hover:text-foreground transition-colors min-w-[220px]",
        )}
      >
        <Search className="h-4 w-4" />
        <span className="flex-1 text-left">Search or jump to…</span>
        <kbd className="text-[10px] rounded border border-border px-1.5 py-0.5">⌘K</kbd>
      </button>

      <NotificationCenter />

      <button
        onClick={toggle}
        data-testid="topbar-theme-toggle"
        aria-label="Toggle theme"
        className="h-9 w-9 rounded-lg hover:bg-foreground/5 flex items-center justify-center"
      >
        {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </button>

      <div className="hidden sm:flex items-center gap-2 pl-2 border-l border-border ml-1">
        <div className="h-8 w-8 rounded-full bg-gradient-to-br from-primary/40 to-cyan-500/40 flex items-center justify-center text-xs font-semibold">
          {(user?.full_name || user?.email || "?").charAt(0).toUpperCase()}
        </div>
        <div className="text-xs leading-tight">
          <div className="font-medium truncate max-w-[120px]">{user?.full_name}</div>
          <div className="text-muted-foreground truncate max-w-[120px] capitalize">{user?.role}</div>
        </div>
      </div>
    </header>
  );
}
