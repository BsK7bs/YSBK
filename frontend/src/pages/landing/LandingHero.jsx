import React, { useEffect, useRef, useState, lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import {
  ArrowRight, PlayCircle, Cpu, MemoryStick, Thermometer, HeartPulse,
  Brain, Bell, Sparkles, ShieldCheck, Radio, Zap,
} from "lucide-react";
import { Button } from "../../components/ui/button";

const HeroScene3D = lazy(() => import("./HeroScene3D"));

/* -------- Small helpers -------- */

const CountUp = ({ to, decimals = 0, suffix = "", duration = 1.6 }) => {
  const [val, setVal] = useState(0);
  const ref = useRef(null);
  useEffect(() => {
    let raf, start;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      const step = (t) => {
        if (!start) start = t;
        const p = Math.min(1, (t - start) / (duration * 1000));
        const eased = 1 - Math.pow(1 - p, 3);
        setVal(eased * to);
        if (p < 1) raf = requestAnimationFrame(step);
      };
      raf = requestAnimationFrame(step);
      io.disconnect();
    }, { threshold: 0.4 });
    if (ref.current) io.observe(ref.current);
    return () => { io.disconnect(); if (raf) cancelAnimationFrame(raf); };
  }, [to, duration]);
  const shown = decimals ? val.toFixed(decimals) : Math.round(val).toLocaleString();
  return <span ref={ref} className="tabular-nums">{shown}{suffix}</span>;
};

/* -------- Floating metric card (parallax + physics) -------- */

const FloatingCard = ({ icon: Icon, label, value, tone, style, delay = 0, mvX, mvY, depth = 1 }) => {
  const x = useTransform(mvX, (v) => v * 12 * depth);
  const y = useTransform(mvY, (v) => v * 12 * depth);
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.85, y: 30 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.7, delay, ease: [0.2, 0.8, 0.2, 1] }}
      style={{ x, y, ...style }}
      className="absolute z-10 w-[160px] hidden sm:block rounded-2xl border border-border/60 bg-card/70 backdrop-blur-xl shadow-[0_20px_60px_-20px_rgba(0,0,0,0.4)] gradient-border"
    >
      <div className="animate-float-slow p-3.5">
        <div className="flex items-center gap-2">
          <div className={`h-8 w-8 rounded-lg flex items-center justify-center ${tone}`}>
            <Icon className="h-4 w-4" />
          </div>
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</div>
        </div>
        <div className="mt-2 text-lg font-bold tabular-nums text-foreground">{value}</div>
      </div>
    </motion.div>
  );
};

/* -------- Laptop dashboard mockup -------- */

const LaptopMock = () => {
  // Live pulsing numbers
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1400);
    return () => clearInterval(id);
  }, []);

  const cpu = 34 + Math.round(Math.sin(tick / 2) * 10 + Math.random() * 4);
  const ram = 58 + Math.round(Math.cos(tick / 3) * 6 + Math.random() * 3);
  const temp = 62 + Math.round(Math.sin(tick / 4) * 5 + Math.random() * 2);
  const health = 91 + Math.round(Math.sin(tick / 5) * 3);

  const bars = Array.from({ length: 48 }, (_, i) =>
    22 + Math.sin((tick + i) / 3.4) * 18 + Math.abs(Math.sin(i / 2)) * 22
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 40, rotateX: 8 }}
      animate={{ opacity: 1, y: 0, rotateX: 0 }}
      transition={{ duration: 0.9, delay: 0.15, ease: [0.2, 0.8, 0.2, 1] }}
      className="relative mx-auto w-full max-w-[640px]"
      style={{ transformPerspective: 1200 }}
    >
      {/* Laptop screen */}
      <div className="relative rounded-[22px] border border-border/70 bg-[hsl(var(--surface))]/95 backdrop-blur-xl shadow-[0_40px_120px_-30px_rgba(0,0,0,0.6)] overflow-hidden">
        {/* top chrome */}
        <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-border/60 bg-background/40">
          <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--critical))]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--warning))]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--success))]" />
          <div className="ml-3 flex items-center gap-1.5 text-[10px] text-muted-foreground">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inset-0 rounded-full bg-emerald-500 animate-ping-soft" />
              <span className="relative rounded-full h-1.5 w-1.5 bg-emerald-500" />
            </span>
            LAB-PC-01 · live telemetry
          </div>
          <div className="ml-auto text-[10px] text-muted-foreground font-mono">app.digitaltwin.io</div>
        </div>

        {/* body */}
        <div className="p-4 grid grid-cols-6 gap-3">
          {/* health score */}
          <div className="col-span-2 rounded-xl border border-border/60 bg-background/50 p-3 relative overflow-hidden">
            <div className="text-[9px] uppercase tracking-widest text-muted-foreground">Health Score</div>
            <div className="mt-2 flex items-center gap-3">
              <div className="relative h-16 w-16">
                <svg viewBox="0 0 36 36" className="h-16 w-16 -rotate-90">
                  <circle cx="18" cy="18" r="15" fill="none" stroke="hsl(var(--border))" strokeWidth="3" />
                  <motion.circle
                    cx="18" cy="18" r="15" fill="none"
                    stroke="url(#healthGrad)" strokeWidth="3" strokeLinecap="round"
                    strokeDasharray="94.2" animate={{ strokeDashoffset: 94.2 - (94.2 * health) / 100 }}
                    transition={{ duration: 1, ease: "easeInOut" }}
                  />
                  <defs>
                    <linearGradient id="healthGrad" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stopColor="hsl(var(--chart-3))" />
                      <stop offset="100%" stopColor="hsl(var(--primary))" />
                    </linearGradient>
                  </defs>
                </svg>
                <div className="absolute inset-0 flex items-center justify-center text-sm font-bold tabular-nums">{health}</div>
              </div>
              <div className="text-[10px]">
                <div className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-[hsl(var(--success))]/15 text-[hsl(var(--success))] font-semibold">EXCELLENT</div>
                <div className="mt-1 text-muted-foreground">Trend improving</div>
              </div>
            </div>
          </div>

          {/* KPIs */}
          {[
            { l: "CPU", v: `${cpu}%`, i: Cpu, c: "text-[hsl(var(--primary))]" },
            { l: "RAM", v: `${ram}%`, i: MemoryStick, c: "text-[hsl(var(--info))]" },
            { l: "TEMP", v: `${temp}°C`, i: Thermometer, c: "text-[hsl(var(--warning))]" },
            { l: "STATUS", v: "Online", i: Radio, c: "text-[hsl(var(--success))]" },
          ].map((k) => (
            <div key={k.l} className="rounded-xl border border-border/60 bg-background/50 p-3">
              <div className="flex items-center justify-between">
                <div className="text-[9px] uppercase tracking-widest text-muted-foreground">{k.l}</div>
                <k.i className={`h-3.5 w-3.5 ${k.c}`} />
              </div>
              <div className="mt-1.5 text-base font-bold tabular-nums">{k.v}</div>
              <div className="mt-1 h-1 w-full rounded-full bg-foreground/[0.06]">
                <motion.div
                  key={`${k.l}-${tick}`}
                  initial={{ width: 0 }}
                  animate={{ width: k.l === "STATUS" ? "100%" : k.v }}
                  transition={{ duration: 0.6 }}
                  className={`h-1 rounded-full ${
                    k.l === "TEMP" ? "bg-[hsl(var(--warning))]" :
                    k.l === "STATUS" ? "bg-[hsl(var(--success))]" :
                    k.l === "RAM" ? "bg-[hsl(var(--info))]" : "bg-[hsl(var(--primary))]"
                  }`}
                />
              </div>
            </div>
          ))}

          {/* Chart */}
          <div className="col-span-4 rounded-xl border border-border/60 bg-background/50 p-3">
            <div className="flex items-center justify-between">
              <div className="text-[10px] uppercase tracking-widest text-muted-foreground">Live Telemetry · 60s</div>
              <div className="flex items-center gap-1 text-[9px] text-muted-foreground">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse-dot" /> streaming
              </div>
            </div>
            <div className="mt-3 h-24 flex items-end gap-[3px]">
              {bars.map((h, i) => (
                <motion.div
                  key={i}
                  animate={{ height: h }}
                  transition={{ duration: 0.5, ease: "easeOut" }}
                  className="flex-1 rounded-t"
                  style={{
                    background: `linear-gradient(180deg, hsl(var(--primary) / 0.9), hsl(var(--info) / 0.5))`,
                  }}
                />
              ))}
            </div>
          </div>

          {/* Alerts feed */}
          <div className="col-span-2 rounded-xl border border-border/60 bg-background/50 p-3">
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-muted-foreground">
              <Bell className="h-3 w-3" /> Recent Alerts
            </div>
            <div className="mt-2 space-y-1.5">
              {[
                { s: "critical", l: "Disk SMART pre-fail", d: "2m" },
                { s: "warning", l: "CPU sustained 92%", d: "8m" },
                { s: "info", l: "Windows update ready", d: "12m" },
              ].map((a, i) => (
                <motion.div
                  key={i}
                  initial={{ x: -20, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  transition={{ delay: 0.4 + i * 0.15, duration: 0.4 }}
                  className="flex items-center gap-2 text-[10px]"
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${
                    a.s === "critical" ? "bg-[hsl(var(--critical))]" :
                    a.s === "warning" ? "bg-[hsl(var(--warning))]" : "bg-[hsl(var(--info))]"
                  }`} />
                  <span className="truncate flex-1">{a.l}</span>
                  <span className="text-muted-foreground">{a.d}</span>
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      </div>
      {/* Laptop base */}
      <div className="relative mx-auto h-3 w-[92%] rounded-b-3xl bg-gradient-to-b from-[hsl(var(--border))] to-transparent" />
      <div className="mx-auto h-2 w-16 rounded-b-xl bg-[hsl(var(--border))]/60" />
      {/* glow under */}
      <div className="absolute -bottom-16 left-1/2 h-24 w-[70%] -translate-x-1/2 rounded-full blur-3xl opacity-70"
        style={{ background: "radial-gradient(ellipse, hsl(var(--primary) / 0.4), transparent 70%)" }} />
    </motion.div>
  );
};

/* -------- Main Hero -------- */

export default function LandingHero() {
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const smx = useSpring(mx, { stiffness: 60, damping: 20 });
  const smy = useSpring(my, { stiffness: 60, damping: 20 });

  const wrapRef = useRef(null);
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const onMove = (e) => {
      const r = el.getBoundingClientRect();
      mx.set((e.clientX - r.left - r.width / 2) / r.width);
      my.set((e.clientY - r.top - r.height / 2) / r.height);
    };
    el.addEventListener("pointermove", onMove);
    return () => el.removeEventListener("pointermove", onMove);
  }, [mx, my]);

  return (
    <section ref={wrapRef} className="relative pt-16 sm:pt-24 pb-24 sm:pb-40 overflow-hidden" data-testid="landing-hero">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10 relative">

        {/* Pill */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="mx-auto w-fit"
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/5 backdrop-blur px-3.5 py-1.5">
            <span className="relative flex h-2 w-2">
              <span className="absolute inset-0 rounded-full bg-primary animate-ping-soft" />
              <span className="relative h-2 w-2 rounded-full bg-primary" />
            </span>
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary">
              Introducing AI Prediction v2 · GA
            </span>
            <Sparkles className="h-3 w-3 text-primary" />
          </div>
        </motion.div>

        {/* Headline */}
        <motion.h1
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 0.1, ease: [0.2, 0.8, 0.2, 1] }}
          className="mt-6 text-center text-[38px] sm:text-6xl lg:text-7xl leading-[1.05] font-extrabold tracking-tight max-w-5xl mx-auto"
        >
          <span className="block">AI Digital Twin Platform for</span>
          <span className="block mt-1 text-gradient-primary animate-shimmer-text">
            Smart Computer Labs
          </span>
          <span className="block mt-1">& Enterprise Device Monitoring</span>
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.25 }}
          className="mt-6 text-center text-base sm:text-lg text-muted-foreground max-w-2xl mx-auto leading-relaxed"
        >
          Live digital twins of every computer you manage. Predict failures before
          they happen, remediate remotely in one click, and prove compliance —
          all from a single real-time dashboard.
        </motion.p>

        {/* CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.4 }}
          className="mt-8 flex flex-wrap items-center justify-center gap-3"
        >
          <Link to="/signup" data-testid="hero-start-trial">
            <Button
              size="lg"
              className="group relative overflow-hidden h-12 px-6 rounded-xl bg-gradient-to-r from-primary via-primary to-[hsl(var(--info))] text-white border-0 shadow-[0_16px_50px_-14px_hsl(var(--primary)/0.75)] hover:shadow-[0_22px_60px_-12px_hsl(var(--primary)/0.9)] transition-all"
            >
              <span className="relative z-10 flex items-center gap-2 font-semibold">
                Start Free Trial <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
              </span>
              <span className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/30 to-transparent group-hover:translate-x-full transition-transform duration-1000" />
            </Button>
          </Link>
          <a href="#preview" data-testid="hero-watch-demo">
            <Button
              size="lg"
              variant="outline"
              className="h-12 px-6 rounded-xl border-border/70 bg-background/40 backdrop-blur hover:bg-foreground/[0.04]"
            >
              <PlayCircle className="h-4 w-4 mr-2" /> Watch Demo
            </Button>
          </a>
        </motion.div>

        {/* Feature strip */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.6 }}
          className="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs text-muted-foreground"
        >
          <span className="inline-flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5" /> SOC 2 Type II</span>
          <span className="opacity-30">·</span>
          <span className="inline-flex items-center gap-1.5"><Zap className="h-3.5 w-3.5" /> 14-day free trial</span>
          <span className="opacity-30">·</span>
          <span className="inline-flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5" /> No credit card</span>
        </motion.div>

        {/* 3D interactive scene + floating cards */}
        <div className="relative mt-14 sm:mt-20 min-h-[560px]">
          {/* Floating cards */}
          <FloatingCard icon={Cpu} label="CPU Usage" value="38%"
            tone="bg-[hsl(var(--primary))]/15 text-[hsl(var(--primary))]"
            style={{ top: "0.5rem", left: "1rem" }}
            delay={0.5} mvX={smx} mvY={smy} depth={1.4} />
          <FloatingCard icon={MemoryStick} label="RAM Usage" value="62%"
            tone="bg-[hsl(var(--info))]/15 text-[hsl(var(--info))]"
            style={{ top: "13rem", left: "-1.5rem" }}
            delay={0.7} mvX={smx} mvY={smy} depth={1.1} />
          <FloatingCard icon={Thermometer} label="Temperature" value="62°C"
            tone="bg-[hsl(var(--warning))]/15 text-[hsl(var(--warning))]"
            style={{ bottom: "0.5rem", left: "1rem" }}
            delay={0.9} mvX={smx} mvY={smy} depth={1.6} />
          <FloatingCard icon={HeartPulse} label="Health" value="94 / 100"
            tone="bg-[hsl(var(--chart-3))]/15 text-[hsl(var(--chart-3))]"
            style={{ top: "0.5rem", right: "1rem" }}
            delay={0.55} mvX={smx} mvY={smy} depth={1.3} />
          <FloatingCard icon={Brain} label="Prediction" value="Fail in 6d"
            tone="bg-[hsl(var(--critical))]/15 text-[hsl(var(--critical))]"
            style={{ top: "13rem", right: "-1.5rem" }}
            delay={0.75} mvX={smx} mvY={smy} depth={1.15} />
          <FloatingCard icon={Bell} label="Alerts" value="2 Critical"
            tone="bg-[hsl(var(--chart-5))]/15 text-[hsl(var(--chart-5))]"
            style={{ bottom: "0.5rem", right: "1rem" }}
            delay={0.95} mvX={smx} mvY={smy} depth={1.5} />

          <Suspense fallback={
            <div className="mx-auto w-full max-w-[640px] h-[440px] rounded-3xl border border-border/60 bg-card/40 backdrop-blur-xl animate-pulse" />
          }>
            <div className="mx-auto w-full max-w-[880px]">
              <HeroScene3D />
            </div>
          </Suspense>
        </div>

        {/* Trust logos strip */}
        <div className="mt-16 sm:mt-24 relative">
          <div className="text-center text-[11px] uppercase tracking-[0.24em] text-muted-foreground mb-6">
            Trusted by IT teams at
          </div>
          <div className="relative overflow-hidden mask-radial-fade">
            <div className="flex gap-14 animate-marquee w-max opacity-60">
              {[...Array(2)].map((_, dup) => (
                <div key={dup} className="flex gap-14 items-center">
                  {["ACME Labs", "Northwind", "Contoso", "Fabrikam", "Umbrella", "Initech", "Wayne Ent.", "Stark Ind."].map((n) => (
                    <div key={n + dup} className="text-lg sm:text-xl font-black tracking-tight whitespace-nowrap text-foreground/70">
                      {n}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* Export CountUp for use in TrustCounters */
export { CountUp };
