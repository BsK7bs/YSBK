import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Cpu, Menu, X, Sun, Moon, ChevronRight } from "lucide-react";
import { useTheme } from "../../contexts/ThemeContext";
import { Button } from "../../components/ui/button";

const NAV = [
  { label: "Features", href: "#features" },
  { label: "Solutions", href: "#solutions" },
  { label: "Pricing", href: "#pricing" },
  { label: "Documentation", href: "#docs" },
  { label: "Contact", href: "#contact" },
];

export default function LandingNavbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const { theme, toggle } = useTheme();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <motion.header
      initial={{ y: -30, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.2, 0.8, 0.2, 1] }}
      className={`sticky top-0 z-50 transition-all duration-300 ${
        scrolled
          ? "backdrop-blur-xl bg-background/70 border-b border-border/60 shadow-[0_10px_40px_-20px_rgba(0,0,0,0.35)]"
          : "bg-transparent"
      }`}
      data-testid="landing-navbar"
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10 h-16 flex items-center gap-6">
        <Link to="/" className="flex items-center gap-2.5" data-testid="landing-logo">
          <div className="relative h-9 w-9 rounded-xl bg-gradient-to-br from-primary to-[hsl(var(--info))] shadow-[0_10px_30px_-8px_hsl(var(--primary)/0.55)] flex items-center justify-center">
            <Cpu className="h-4.5 w-4.5 text-white" strokeWidth={2.4} />
            <span className="absolute inset-0 rounded-xl ring-1 ring-white/20" />
          </div>
          <div className="leading-tight">
            <div className="text-[15px] font-bold tracking-tight">Digital Twin</div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Enterprise Cloud</div>
          </div>
        </Link>

        <nav className="hidden md:flex items-center gap-1 ml-4">
          {NAV.map((n) => (
            <a
              key={n.label}
              href={n.href}
              className="relative px-3 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors group"
              data-testid={`nav-${n.label.toLowerCase()}`}
            >
              {n.label}
              <span className="absolute inset-x-3 -bottom-0.5 h-px bg-gradient-to-r from-transparent via-primary to-transparent scale-x-0 group-hover:scale-x-100 transition-transform origin-center" />
            </a>
          ))}
        </nav>

        <div className="flex-1" />

        <button
          onClick={toggle}
          className="hidden sm:inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border/70 bg-background/40 backdrop-blur hover:bg-foreground/[0.04] transition"
          aria-label="Toggle theme"
          data-testid="landing-theme-toggle"
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={theme}
              initial={{ rotate: -90, opacity: 0 }}
              animate={{ rotate: 0, opacity: 1 }}
              exit={{ rotate: 90, opacity: 0 }}
              transition={{ duration: 0.25 }}
              className="inline-flex"
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </motion.span>
          </AnimatePresence>
        </button>

        <Link to="/login" className="hidden sm:inline-block text-sm text-muted-foreground hover:text-foreground transition-colors" data-testid="nav-login">
          Login
        </Link>
        <Link to="/signup" data-testid="nav-get-started">
          <Button
            size="sm"
            className="relative overflow-hidden bg-gradient-to-r from-primary to-[hsl(var(--info))] text-white shadow-[0_10px_30px_-10px_hsl(var(--primary)/0.7)] hover:shadow-[0_14px_36px_-8px_hsl(var(--primary)/0.85)] transition-all border-0"
          >
            <span className="relative z-10 flex items-center gap-1.5">
              Get Started <ChevronRight className="h-3.5 w-3.5" />
            </span>
            <span className="absolute inset-0 bg-white/20 opacity-0 hover:opacity-100 transition-opacity" />
          </Button>
        </Link>

        <button
          className="md:hidden h-9 w-9 rounded-lg border border-border/70 flex items-center justify-center"
          onClick={() => setOpen((v) => !v)}
          aria-label="Toggle menu"
          data-testid="landing-mobile-menu"
        >
          {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
        </button>
      </div>

      {/* Mobile menu */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="md:hidden overflow-hidden border-t border-border/60 bg-background/90 backdrop-blur-xl"
          >
            <div className="px-4 py-4 space-y-1">
              {NAV.map((n) => (
                <a key={n.label} href={n.href} onClick={() => setOpen(false)}
                   className="block px-3 py-2.5 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04]">
                  {n.label}
                </a>
              ))}
              <div className="pt-2 flex gap-2">
                <Link to="/login" className="flex-1" onClick={() => setOpen(false)}>
                  <Button variant="outline" size="sm" className="w-full">Login</Button>
                </Link>
                <Link to="/signup" className="flex-1" onClick={() => setOpen(false)}>
                  <Button size="sm" className="w-full bg-gradient-to-r from-primary to-[hsl(var(--info))] text-white border-0">Get Started</Button>
                </Link>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  );
}
