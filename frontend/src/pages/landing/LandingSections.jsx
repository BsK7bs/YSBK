import React from "react";
import { motion } from "framer-motion";
import {
  Cpu, Brain, HeartPulse, Activity, Terminal, Bot, Boxes, ShieldCheck,
  Wrench, LineChart, X, Check, TrendingDown, CircuitBoard, Clock, Eye,
  AlertTriangle, Sparkles, Gauge, Radio, MonitorSmartphone,
  ChevronDown, Twitter, Github, Linkedin, Mail, ArrowRight, Star,
  MapPin, Download, MousePointerClick, Server,
} from "lucide-react";
import { Link } from "react-router-dom";
import { CountUp } from "./LandingHero";
import { Button } from "../../components/ui/button";
import {
  Accordion, AccordionContent, AccordionItem, AccordionTrigger,
} from "../../components/ui/accordion";

/* ================= reveal helper ================= */

const reveal = (delay = 0) => ({
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, amount: 0.25 },
  transition: { duration: 0.6, delay, ease: [0.2, 0.8, 0.2, 1] },
});

/* ================= Trust Counters ================= */

export const TrustCounters = () => {
  const items = [
    { v: 10000, s: "+", label: "Devices Monitored" },
    { v: 99.99, s: "%", dec: 2, label: "Platform Uptime" },
    { v: 500, s: "+", label: "Organizations" },
    { v: 1000000, s: "+", label: "Telemetry Events / day" },
  ];
  return (
    <section className="relative py-20 sm:py-28" data-testid="landing-trust">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
        <motion.div {...reveal()} className="text-center">
          <div className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">
            Numbers speak
          </div>
          <h2 className="mt-3 text-3xl sm:text-5xl font-extrabold tracking-tight">
            Enterprise scale, <span className="text-gradient-primary">battle tested</span>.
          </h2>
        </motion.div>

        <div className="mt-12 grid grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
          {items.map((it, i) => (
            <motion.div
              key={it.label}
              {...reveal(i * 0.08)}
              className="relative rounded-2xl border border-border/60 bg-card/40 backdrop-blur-xl p-6 sm:p-7 gradient-border overflow-hidden group"
            >
              <div className="absolute -top-16 -right-16 h-40 w-40 rounded-full blur-3xl opacity-40 group-hover:opacity-70 transition-opacity"
                style={{ background: "radial-gradient(circle, hsl(var(--primary) / 0.6), transparent 70%)" }} />
              <div className="relative">
                <div className="text-4xl sm:text-5xl font-extrabold tracking-tight">
                  <CountUp to={it.v} decimals={it.dec || 0} suffix={it.s} />
                </div>
                <div className="mt-2 text-xs sm:text-sm text-muted-foreground uppercase tracking-widest">
                  {it.label}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ================= Problem / Solution ================= */

export const ProblemSolution = () => {
  const problems = [
    { i: Eye, t: "Manual monitoring", d: "Techs spread across dozens of spreadsheets and remote-desktop sessions." },
    { i: AlertTriangle, t: "Unexpected failures", d: "Drives, PSUs and fans die without warning — users lose work." },
    { i: Clock, t: "Hardware downtime", d: "Hours lost per incident. No visibility until users file a ticket." },
    { i: TrendingDown, t: "No predictions", d: "You react to problems instead of preventing them." },
  ];
  const solutions = [
    { i: Brain, t: "AI failure prediction", d: "ML models forecast SSD/fan/battery failure days in advance." },
    { i: CircuitBoard, t: "Digital Twin", d: "Every machine mirrored live — CPU, RAM, temp, disk, network, users." },
    { i: HeartPulse, t: "Explainable Health Score", d: "0–100 score with per-metric deductions and recommendations." },
    { i: Radio, t: "Real-time alerts", d: "Sub-second WebSocket updates with dwell suppression to kill noise." },
  ];

  return (
    <section id="solutions" className="relative py-20 sm:py-28" data-testid="landing-problem-solution">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
        <motion.div {...reveal()} className="text-center max-w-2xl mx-auto">
          <div className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">
            Old way vs Digital Twin
          </div>
          <h2 className="mt-3 text-3xl sm:text-5xl font-extrabold tracking-tight">
            Stop reacting.<br/>
            <span className="text-gradient-primary">Start predicting.</span>
          </h2>
        </motion.div>

        <div className="mt-14 grid lg:grid-cols-2 gap-6">
          {/* problems */}
          <motion.div {...reveal(0.05)} className="rounded-3xl border border-[hsl(var(--critical))]/25 bg-gradient-to-b from-[hsl(var(--critical))]/[0.06] to-transparent p-6 sm:p-8">
            <div className="flex items-center gap-2 mb-6">
              <div className="h-9 w-9 rounded-xl bg-[hsl(var(--critical))]/15 text-[hsl(var(--critical))] flex items-center justify-center">
                <X className="h-5 w-5" strokeWidth={2.5} />
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-[hsl(var(--critical))] font-semibold">Problems</div>
                <div className="font-bold">Legacy IT monitoring</div>
              </div>
            </div>
            <div className="space-y-3">
              {problems.map((p, i) => (
                <motion.div key={p.t} {...reveal(0.1 + i * 0.06)}
                  className="flex items-start gap-3 rounded-xl border border-border/50 bg-background/40 backdrop-blur p-4">
                  <p.i className="h-4 w-4 mt-0.5 text-[hsl(var(--critical))]" />
                  <div>
                    <div className="text-sm font-semibold">{p.t}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">{p.d}</div>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>

          {/* solutions */}
          <motion.div {...reveal(0.1)} className="rounded-3xl border border-[hsl(var(--success))]/25 bg-gradient-to-b from-[hsl(var(--success))]/[0.06] to-transparent p-6 sm:p-8">
            <div className="flex items-center gap-2 mb-6">
              <div className="h-9 w-9 rounded-xl bg-[hsl(var(--success))]/15 text-[hsl(var(--success))] flex items-center justify-center">
                <Check className="h-5 w-5" strokeWidth={2.5} />
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-[hsl(var(--success))] font-semibold">Solutions</div>
                <div className="font-bold">Digital Twin Platform</div>
              </div>
            </div>
            <div className="space-y-3">
              {solutions.map((p, i) => (
                <motion.div key={p.t} {...reveal(0.15 + i * 0.06)}
                  className="flex items-start gap-3 rounded-xl border border-border/50 bg-background/40 backdrop-blur p-4">
                  <p.i className="h-4 w-4 mt-0.5 text-[hsl(var(--success))]" />
                  <div>
                    <div className="text-sm font-semibold">{p.t}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">{p.d}</div>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
};

/* ================= Features Grid ================= */

const FEATURES = [
  { i: CircuitBoard, t: "Digital Twin", d: "Live-mirrored state of every managed computer — hardware, software, users, network.", c: "from-[hsl(var(--primary))]/40 to-[hsl(var(--info))]/20" },
  { i: Brain, t: "Predictive Maintenance", d: "ML models score SSD, fan, battery, thermal & network risks with confidence bands.", c: "from-[hsl(var(--chart-3))]/40 to-[hsl(var(--primary))]/20" },
  { i: HeartPulse, t: "Health Score Engine", d: "Explainable 0–100 score with per-metric deductions, trend & timeline.", c: "from-[hsl(var(--success))]/40 to-[hsl(var(--info))]/20" },
  { i: Activity, t: "Live Monitoring", d: "Sub-second WebSocket telemetry with tenant isolation and 100k+ devices per org.", c: "from-[hsl(var(--info))]/40 to-[hsl(var(--primary))]/20" },
  { i: Terminal, t: "Remote Commands", d: "20+ RBAC-gated actions: restart, script, kill process, collect diagnostics, install / uninstall.", c: "from-[hsl(var(--warning))]/40 to-[hsl(var(--chart-5))]/20" },
  { i: Bot, t: "AI Assistant", d: "Ask “what's wrong with LAB-14?” and get natural-language RCA plus one-click remediations.", c: "from-[hsl(var(--chart-3))]/40 to-[hsl(var(--success))]/20" },
  { i: Boxes, t: "Asset Management", d: "Auto-discovered hardware, warranty, lifecycle, groups, tags and location.", c: "from-[hsl(var(--primary))]/40 to-[hsl(var(--chart-3))]/20" },
  { i: ShieldCheck, t: "Software Compliance", d: "Allowlist / blocklist policies, license usage, CVE alerts, compliance score.", c: "from-[hsl(var(--info))]/40 to-[hsl(var(--success))]/20" },
  { i: Wrench, t: "Maintenance Tickets", d: "Auto-tickets on threshold breach, escalation policies, MTTR reporting.", c: "from-[hsl(var(--chart-5))]/40 to-[hsl(var(--warning))]/20" },
  { i: LineChart, t: "Reports & Analytics", d: "Fleet uptime, health trends, MTBF, energy usage, exportable board-ready reports.", c: "from-[hsl(var(--primary))]/40 to-[hsl(var(--info))]/20" },
];

export const FeaturesGrid = () => (
  <section id="features" className="relative py-20 sm:py-28" data-testid="landing-features">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
      <motion.div {...reveal()} className="text-center max-w-2xl mx-auto">
        <div className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Platform</div>
        <h2 className="mt-3 text-3xl sm:text-5xl font-extrabold tracking-tight">
          Everything IT teams need,<br />
          <span className="text-gradient-primary">in one live dashboard.</span>
        </h2>
        <p className="mt-4 text-muted-foreground">
          Ten first-class modules — not a bundle of Chrome tabs.
        </p>
      </motion.div>

      <div className="mt-14 grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4 sm:gap-5">
        {FEATURES.map((f, i) => (
          <motion.div key={f.t} {...reveal((i % 5) * 0.05)}
            className="group relative rounded-2xl border border-border/60 bg-card/50 backdrop-blur-xl overflow-hidden gradient-border transition-transform hover:-translate-y-1"
          >
            <div className={`absolute -top-24 -right-24 h-56 w-56 rounded-full blur-3xl opacity-40 group-hover:opacity-80 transition-opacity bg-gradient-to-br ${f.c}`} />
            <div className="relative p-5 sm:p-6">
              <div className="h-11 w-11 rounded-xl bg-gradient-to-br from-primary/25 to-[hsl(var(--info))]/20 border border-primary/30 flex items-center justify-center shadow-[0_10px_30px_-15px_hsl(var(--primary)/0.7)]">
                <f.i className="h-5 w-5 text-primary" strokeWidth={2.2} />
              </div>
              <div className="mt-4 font-bold tracking-tight">{f.t}</div>
              <div className="mt-1.5 text-xs text-muted-foreground leading-relaxed">{f.d}</div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  </section>
);

/* ================= Live Dashboard Preview ================= */

export const DashboardPreview = () => {
  const [tick, setTick] = React.useState(0);
  React.useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1200);
    return () => clearInterval(id);
  }, []);
  const cpu = 34 + Math.round(Math.sin(tick / 2) * 12 + Math.random() * 4);
  const ram = 61 + Math.round(Math.cos(tick / 3) * 6);
  const temp = 64 + Math.round(Math.sin(tick / 4) * 5);
  const health = 88 + Math.round(Math.sin(tick / 5) * 4);
  const online = 428 + Math.round(Math.sin(tick / 6) * 3);
  const areaPoints = Array.from({ length: 32 }, (_, i) =>
    36 + Math.sin((tick + i) / 3.6) * 14 + Math.sin(i / 2) * 6
  );

  const Gauge = ({ label, value, unit = "%", color }) => (
    <div className="rounded-xl border border-border/60 bg-background/50 p-4">
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</div>
        <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse-dot" />
      </div>
      <div className="mt-2 flex items-baseline gap-1">
        <span className="text-3xl font-extrabold tabular-nums" style={{ color }}>{value}</span>
        <span className="text-sm text-muted-foreground">{unit}</span>
      </div>
      <div className="mt-3 h-1.5 rounded-full bg-foreground/[0.06] overflow-hidden">
        <motion.div
          animate={{ width: `${Math.min(100, typeof value === "number" ? value : 60)}%` }}
          transition={{ duration: 0.6 }}
          className="h-full rounded-full"
          style={{ background: `linear-gradient(90deg, ${color}, hsl(var(--info)))` }}
        />
      </div>
    </div>
  );

  return (
    <section id="preview" className="relative py-20 sm:py-28" data-testid="landing-dashboard-preview">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
        <motion.div {...reveal()} className="text-center max-w-2xl mx-auto">
          <div className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Live preview</div>
          <h2 className="mt-3 text-3xl sm:text-5xl font-extrabold tracking-tight">
            The <span className="text-gradient-primary">command center</span> for your fleet.
          </h2>
          <p className="mt-4 text-muted-foreground">
            Everything below is streaming — not a screenshot.
          </p>
        </motion.div>

        <motion.div {...reveal(0.05)} className="mt-12 relative rounded-3xl border border-border/70 bg-card/60 backdrop-blur-xl overflow-hidden gradient-border shadow-[0_60px_140px_-40px_rgba(0,0,0,0.6)]">
          {/* topbar */}
          <div className="flex items-center gap-3 px-5 py-3 border-b border-border/60 bg-background/40">
            <div className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--critical))]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--warning))]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--success))]" />
            </div>
            <div className="ml-2 text-xs font-semibold">Fleet Overview</div>
            <div className="ml-3 inline-flex items-center gap-1.5 rounded-full bg-[hsl(var(--success))]/15 text-[hsl(var(--success))] px-2 py-0.5 text-[10px] font-semibold">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inset-0 rounded-full bg-emerald-500 animate-ping-soft" />
                <span className="relative h-1.5 w-1.5 rounded-full bg-emerald-500" />
              </span>
              LIVE
            </div>
            <div className="ml-auto flex items-center gap-2 text-[10px] text-muted-foreground font-mono">
              app.digitaltwin.io / dashboard
            </div>
          </div>

          <div className="p-5 sm:p-6 grid grid-cols-12 gap-4">
            <div className="col-span-12 sm:col-span-3"><Gauge label="CPU (avg)" value={cpu} color="hsl(var(--primary))" /></div>
            <div className="col-span-12 sm:col-span-3"><Gauge label="RAM (avg)" value={ram} color="hsl(var(--info))" /></div>
            <div className="col-span-12 sm:col-span-3"><Gauge label="Temp (avg)" value={temp} unit="°C" color="hsl(var(--warning))" /></div>
            <div className="col-span-12 sm:col-span-3"><Gauge label="Health" value={health} color="hsl(var(--chart-3))" /></div>

            {/* Chart */}
            <div className="col-span-12 lg:col-span-8 rounded-xl border border-border/60 bg-background/50 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-muted-foreground">Fleet CPU · last 60 min</div>
                  <div className="text-lg font-bold mt-0.5 tabular-nums">{cpu}<span className="text-sm text-muted-foreground">% avg</span></div>
                </div>
                <div className="flex items-center gap-2 text-[10px]">
                  <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-[hsl(var(--primary))]" /> CPU</span>
                  <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-[hsl(var(--info))]" /> Baseline</span>
                </div>
              </div>
              <svg viewBox="0 0 640 160" className="mt-3 w-full h-40">
                <defs>
                  <linearGradient id="cpuArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity="0.6" />
                    <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity="0.02" />
                  </linearGradient>
                </defs>
                {/* grid */}
                {[0, 40, 80, 120].map((y) => (
                  <line key={y} x1="0" x2="640" y1={y} y2={y} stroke="hsl(var(--border))" strokeWidth="1" />
                ))}
                <motion.path
                  key={tick}
                  initial={{ pathLength: 0.3, opacity: 0.6 }}
                  animate={{ pathLength: 1, opacity: 1 }}
                  transition={{ duration: 1 }}
                  d={
                    "M 0 " + (140 - areaPoints[0]) +
                    areaPoints.map((v, i) => ` L ${(i * 640) / (areaPoints.length - 1)} ${140 - v}`).join("") +
                    " L 640 160 L 0 160 Z"
                  }
                  fill="url(#cpuArea)"
                />
                <path
                  d={
                    "M 0 " + (140 - areaPoints[0]) +
                    areaPoints.map((v, i) => ` L ${(i * 640) / (areaPoints.length - 1)} ${140 - v}`).join("")
                  }
                  fill="none" stroke="hsl(var(--primary))" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                />
              </svg>
            </div>

            {/* Prediction & alerts */}
            <div className="col-span-12 lg:col-span-4 space-y-4">
              <div className="rounded-xl border border-border/60 bg-background/50 p-4">
                <div className="flex items-center gap-2">
                  <Brain className="h-4 w-4 text-[hsl(var(--chart-3))]" />
                  <div className="text-[10px] uppercase tracking-widest text-muted-foreground">AI Prediction</div>
                </div>
                <div className="mt-3 text-xs">
                  <div className="font-semibold">LAB-27 · SSD failure in <span className="text-[hsl(var(--critical))]">6 days</span></div>
                  <div className="text-muted-foreground mt-0.5">Confidence 87% · Reallocated sector rising</div>
                </div>
                <div className="mt-3 h-2 rounded-full bg-foreground/[0.06] overflow-hidden">
                  <motion.div animate={{ width: "87%" }} transition={{ duration: 1 }} className="h-full rounded-full bg-gradient-to-r from-[hsl(var(--chart-3))] to-[hsl(var(--critical))]" />
                </div>
              </div>
              <div className="rounded-xl border border-border/60 bg-background/50 p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Radio className="h-4 w-4 text-[hsl(var(--info))]" />
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground">Online devices</div>
                  </div>
                  <span className="text-[10px] text-[hsl(var(--success))]">+2</span>
                </div>
                <div className="mt-2 text-2xl font-extrabold tabular-nums">{online}<span className="text-sm text-muted-foreground">/ 512</span></div>
              </div>
            </div>

            {/* Activity feed */}
            <div className="col-span-12 rounded-xl border border-border/60 bg-background/50 p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground">Live activity</div>
                <span className="inline-flex items-center gap-1 text-[10px] text-[hsl(var(--success))]">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse-dot" /> streaming
                </span>
              </div>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
                {[
                  { i: AlertTriangle, c: "text-[hsl(var(--critical))]", t: "LAB-14 · Temp 92°C sustained 12m", w: "12s" },
                  { i: Check, c: "text-[hsl(var(--success))]", t: "LAB-08 · Windows update installed", w: "34s" },
                  { i: Terminal, c: "text-[hsl(var(--info))]", t: "LAB-22 · Remote restart executed", w: "58s" },
                  { i: Brain, c: "text-[hsl(var(--chart-3))]", t: "LAB-27 · SSD failure risk raised", w: "1m" },
                  { i: ShieldCheck, c: "text-[hsl(var(--success))]", t: "LAB-11 · Antivirus definitions updated", w: "2m" },
                  { i: MonitorSmartphone, c: "text-[hsl(var(--info))]", t: "LAB-42 · Enrolled with agent v2.4.1", w: "3m" },
                ].map((a, i) => (
                  <motion.div key={i}
                    initial={{ opacity: 0, x: -12 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.08 }}
                    className="flex items-center gap-2 rounded-lg border border-border/50 bg-background/40 px-3 py-2 text-[11px]">
                    <a.i className={`h-3.5 w-3.5 ${a.c}`} />
                    <span className="truncate flex-1">{a.t}</span>
                    <span className="text-muted-foreground tabular-nums">{a.w}</span>
                  </motion.div>
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
};

/* ================= How it works timeline ================= */

export const HowItWorks = () => {
  const steps = [
    { i: Download, t: "Download the Agent", d: "Lightweight signed installer for Windows, macOS & Linux.", c: "hsl(var(--primary))" },
    { i: MousePointerClick, t: "One-click Install", d: "Runs as a background service, auto-starts at boot.", c: "hsl(var(--info))" },
    { i: Sparkles, t: "Automatic Enrollment", d: "Paste an org enrollment code — device joins its tenant.", c: "hsl(var(--chart-3))" },
    { i: Activity, t: "Live Monitoring", d: "Telemetry streams in real time — hardware, users, software.", c: "hsl(var(--success))" },
    { i: Brain, t: "AI Predictions", d: "Failure forecasts + auto-triage recommendations begin flowing.", c: "hsl(var(--chart-5))" },
  ];
  return (
    <section id="how" className="relative py-20 sm:py-28" data-testid="landing-how">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
        <motion.div {...reveal()} className="text-center max-w-2xl mx-auto">
          <div className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">How it works</div>
          <h2 className="mt-3 text-3xl sm:text-5xl font-extrabold tracking-tight">
            From zero to live twin in <span className="text-gradient-primary">under 4 minutes</span>.
          </h2>
        </motion.div>
        <div className="mt-14 relative">
          <div aria-hidden className="hidden lg:block absolute left-1/2 top-4 bottom-4 w-px bg-gradient-to-b from-transparent via-border to-transparent" />
          <div className="space-y-6 lg:space-y-0">
            {steps.map((s, i) => (
              <motion.div key={s.t} {...reveal(i * 0.06)}
                className={`relative lg:grid lg:grid-cols-9 lg:items-center ${i % 2 ? "lg:[direction:rtl]" : ""}`}>
                <div className="lg:col-span-4 [direction:ltr]">
                  <div className="relative rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl p-5 gradient-border overflow-hidden">
                    <div className="absolute -top-10 -right-10 h-32 w-32 rounded-full blur-3xl opacity-40"
                      style={{ background: `radial-gradient(circle, ${s.c}, transparent 70%)` }} />
                    <div className="relative flex items-center gap-3">
                      <div className="h-11 w-11 rounded-xl border border-border/60 flex items-center justify-center bg-background/60"
                        style={{ color: s.c }}>
                        <s.i className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="text-[10px] uppercase tracking-widest text-muted-foreground">Step {i + 1}</div>
                        <div className="font-bold">{s.t}</div>
                      </div>
                    </div>
                    <div className="relative mt-3 text-xs text-muted-foreground">{s.d}</div>
                  </div>
                </div>
                <div className="hidden lg:flex lg:col-span-1 justify-center [direction:ltr]">
                  <div className="relative h-8 w-8 rounded-full bg-background border border-border flex items-center justify-center text-[11px] font-bold">
                    {i + 1}
                    <span className="absolute inset-0 rounded-full ring-2 ring-primary/40 animate-ping-soft" />
                  </div>
                </div>
                <div className="hidden lg:block lg:col-span-4" />
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

/* ================= Comparison ================= */

export const Comparison = () => {
  const rows = [
    ["Real-time telemetry (WebSocket)", false, "partial", true],
    ["Digital Twin per device", false, false, true],
    ["AI failure prediction", false, false, true],
    ["Explainable Health Score", false, false, true],
    ["Remote actions (RBAC)", "manual", "partial", true],
    ["Multi-tenant isolation", false, "partial", true],
    ["Software policy & compliance", false, "partial", true],
    ["Deploy in < 4 minutes", false, false, true],
  ];
  const Cell = ({ v }) =>
    v === true ? (
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-[hsl(var(--success))]/15 text-[hsl(var(--success))]">
        <Check className="h-3.5 w-3.5" strokeWidth={3} />
      </span>
    ) : v === false ? (
      <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-[hsl(var(--critical))]/15 text-[hsl(var(--critical))]">
        <X className="h-3.5 w-3.5" strokeWidth={3} />
      </span>
    ) : (
      <span className="text-[10px] uppercase tracking-widest text-[hsl(var(--warning))] font-semibold">{v}</span>
    );

  return (
    <section id="why" className="relative py-20 sm:py-28" data-testid="landing-comparison">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
        <motion.div {...reveal()} className="text-center max-w-2xl mx-auto">
          <div className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Why choose us</div>
          <h2 className="mt-3 text-3xl sm:text-5xl font-extrabold tracking-tight">
            The <span className="text-gradient-primary">only platform</span> built for digital twins.
          </h2>
        </motion.div>

        <motion.div {...reveal(0.05)} className="mt-12 rounded-3xl border border-border/70 bg-card/50 backdrop-blur-xl overflow-hidden">
          <div className="grid grid-cols-4 items-stretch">
            <div className="px-5 py-4 text-[10px] uppercase tracking-widest text-muted-foreground">Capability</div>
            <div className="px-5 py-4 text-center text-xs font-semibold text-muted-foreground border-l border-border/60">
              Traditional Lab Monitoring
            </div>
            <div className="px-5 py-4 text-center text-xs font-semibold text-muted-foreground border-l border-border/60">
              Basic Monitoring Software
            </div>
            <div className="relative px-5 py-4 text-center border-l border-border/60 bg-gradient-to-b from-primary/15 to-transparent">
              <div className="text-xs font-bold text-primary">Digital Twin Platform</div>
              <span className="absolute top-2 right-2 text-[9px] px-1.5 py-0.5 rounded-md bg-primary text-white font-semibold">RECOMMENDED</span>
            </div>
          </div>
          {rows.map((r, i) => (
            <motion.div key={r[0]} {...reveal(i * 0.04)}
              className="grid grid-cols-4 items-center border-t border-border/50 hover:bg-foreground/[0.02] transition-colors">
              <div className="px-5 py-4 text-sm">{r[0]}</div>
              <div className="px-5 py-4 flex justify-center border-l border-border/60"><Cell v={r[1]} /></div>
              <div className="px-5 py-4 flex justify-center border-l border-border/60"><Cell v={r[2]} /></div>
              <div className="px-5 py-4 flex justify-center border-l border-border/60 bg-primary/[0.03]"><Cell v={r[3]} /></div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
};

/* ================= Testimonials ================= */

const TESTIMONIALS = [
  { n: "Priya S.", r: "Head of IT · Bay Area STEM Academy", q: "We caught 12 SSD failures before they took down classrooms this semester. Board-level metric now.", i: "PS", c: "from-[hsl(var(--primary))] to-[hsl(var(--info))]" },
  { n: "Marcus D.", r: "MSP Founder · Northwind IT", q: "Onboarded 47 client fleets in a week. The digital twin view sells itself to non-technical stakeholders.", i: "MD", c: "from-[hsl(var(--chart-3))] to-[hsl(var(--info))]" },
  { n: "Aisha K.", r: "SRE · Contoso Retail", q: "Alert noise dropped 80% overnight thanks to dwell suppression. My on-call sleeps again.", i: "AK", c: "from-[hsl(var(--warning))] to-[hsl(var(--critical))]" },
  { n: "Diego R.", r: "Director of IT · UniLab", q: "The remote command RBAC is best-in-class. Our compliance auditor gave us a rare unqualified pass.", i: "DR", c: "from-[hsl(var(--success))] to-[hsl(var(--chart-3))]" },
  { n: "Yuki T.", r: "Ops Lead · Fabrikam Cloud", q: "AI prediction paid for the platform in two weeks. Nothing else even comes close.", i: "YT", c: "from-[hsl(var(--info))] to-[hsl(var(--primary))]" },
  { n: "Lena F.", r: "IT Manager · Stark Industries", q: "Everything a Fortune 500 IT team wants — RBAC, multi-tenant, live twin, and beautiful UI.", i: "LF", c: "from-[hsl(var(--chart-5))] to-[hsl(var(--warning))]" },
];

export const Testimonials = () => (
  <section id="testimonials" className="relative py-20 sm:py-28" data-testid="landing-testimonials">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
      <motion.div {...reveal()} className="text-center max-w-2xl mx-auto">
        <div className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Loved by IT teams</div>
        <h2 className="mt-3 text-3xl sm:text-5xl font-extrabold tracking-tight">
          Built by IT.<br />
          <span className="text-gradient-primary">Chosen by IT.</span>
        </h2>
      </motion.div>
    </div>

    <div className="mt-14 overflow-hidden mask-radial-fade">
      <div className="flex gap-5 animate-marquee w-max">
        {[...TESTIMONIALS, ...TESTIMONIALS].map((t, i) => (
          <div key={i} className="w-[340px] shrink-0 rounded-2xl border border-border/60 bg-card/60 backdrop-blur-xl p-5 gradient-border">
            <div className="flex gap-0.5 mb-3">
              {Array.from({ length: 5 }).map((_, s) => (
                <Star key={s} className="h-3.5 w-3.5 fill-[hsl(var(--warning))] text-[hsl(var(--warning))]" />
              ))}
            </div>
            <div className="text-sm leading-relaxed">"{t.q}"</div>
            <div className="mt-4 flex items-center gap-3">
              <div className={`h-9 w-9 rounded-full bg-gradient-to-br ${t.c} text-white text-xs font-bold flex items-center justify-center`}>
                {t.i}
              </div>
              <div className="text-xs">
                <div className="font-semibold">{t.n}</div>
                <div className="text-muted-foreground">{t.r}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  </section>
);

/* ================= Pricing ================= */

const PLANS = [
  { name: "Starter", price: "Free", period: "/ forever", desc: "For labs & small teams.", cta: "Start Free", highlight: false,
    features: ["Up to 25 devices", "Live monitoring", "Basic alerts", "Community support"] },
  { name: "Business", price: "$4", period: "/ device / mo", desc: "For growing IT & MSPs.", cta: "Start 14-day trial", highlight: true,
    features: ["Unlimited devices", "AI failure prediction", "Health Score engine", "Remote actions & scripts", "Software policy", "Priority support"] },
  { name: "Enterprise", price: "Custom", period: "", desc: "Air-gapped, SSO, SLAs.", cta: "Talk to Sales", highlight: false,
    features: ["Everything in Business", "SAML SSO / SCIM", "Self-hosted option", "Dedicated CSM", "99.99% SLA", "Custom integrations"] },
];

export const Pricing = () => (
  <section id="pricing" className="relative py-20 sm:py-28" data-testid="landing-pricing">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
      <motion.div {...reveal()} className="text-center max-w-2xl mx-auto">
        <div className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Pricing</div>
        <h2 className="mt-3 text-3xl sm:text-5xl font-extrabold tracking-tight">
          Fair, transparent, <span className="text-gradient-primary">per-device pricing</span>.
        </h2>
        <p className="mt-4 text-muted-foreground">Start free. Upgrade when your fleet is ready. No per-seat surprises.</p>
      </motion.div>

      <div className="mt-14 grid md:grid-cols-3 gap-5">
        {PLANS.map((p, i) => (
          <motion.div key={p.name} {...reveal(i * 0.08)}
            className={`group relative rounded-3xl border p-6 sm:p-7 transition-transform hover:-translate-y-1
            ${p.highlight
              ? "border-primary/40 bg-gradient-to-b from-primary/10 to-transparent shadow-[0_30px_80px_-30px_hsl(var(--primary)/0.6)]"
              : "border-border/60 bg-card/50 backdrop-blur-xl gradient-border"}`}
          >
            {p.highlight && (
              <>
                <div className="absolute inset-0 rounded-3xl opacity-70 pointer-events-none"
                  style={{ background: "radial-gradient(80% 60% at 50% 0%, hsl(var(--primary) / 0.18), transparent 70%)" }} />
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-full bg-gradient-to-r from-primary to-[hsl(var(--info))] text-white shadow-[0_10px_30px_-10px_hsl(var(--primary)/0.8)]">
                  Most popular
                </span>
              </>
            )}
            <div className="relative">
              <div className="text-sm font-semibold">{p.name}</div>
              <div className="mt-3 flex items-baseline gap-1">
                <div className="text-4xl font-extrabold tracking-tight">{p.price}</div>
                <div className="text-sm text-muted-foreground">{p.period}</div>
              </div>
              <div className="mt-1.5 text-xs text-muted-foreground">{p.desc}</div>
              <ul className="mt-5 space-y-2.5">
                {p.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm">
                    <Check className="h-4 w-4 mt-0.5 text-[hsl(var(--success))]" strokeWidth={2.5} />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <Link to="/signup" className="block mt-6" data-testid={`pricing-cta-${p.name.toLowerCase()}`}>
                <Button className={`w-full h-11 rounded-xl ${p.highlight
                  ? "bg-gradient-to-r from-primary to-[hsl(var(--info))] text-white border-0 shadow-[0_16px_40px_-14px_hsl(var(--primary)/0.7)]"
                  : ""}`}
                  variant={p.highlight ? "default" : "outline"}
                >
                  {p.cta} <ArrowRight className="h-4 w-4 ml-1.5" />
                </Button>
              </Link>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  </section>
);

/* ================= FAQ ================= */

const FAQS = [
  { q: "How is a “digital twin” different from monitoring?", a: "A twin holds live state — hardware, users, running processes, software inventory, health score, prediction — not just metrics. You can query and act on it in real time." },
  { q: "Do I need to install anything?", a: "A small signed background agent runs on each managed computer. It uses no invasive data collection (no screen, keys, mic, cam) and can be uninstalled at any time." },
  { q: "Is the platform multi-tenant?", a: "Yes. Every read and write is scoped by org_id at the DB layer. Data isolation is tested by our POC suite on every release." },
  { q: "What OSes are supported?", a: "Windows 10/11 today (agent v2). macOS & Linux agents are in private beta." },
  { q: "Can I self-host?", a: "Yes — on the Enterprise plan. You get container images, a Helm chart, and a signed offline update channel." },
  { q: "How accurate is failure prediction?", a: "We publish per-model precision / recall in the app. Current SSD model reaches ~87% precision at a 7-day horizon on our reference fleet." },
];

export const FAQ = () => (
  <section id="faq" className="relative py-20 sm:py-28" data-testid="landing-faq">
    <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-10">
      <motion.div {...reveal()} className="text-center">
        <div className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">FAQ</div>
        <h2 className="mt-3 text-3xl sm:text-5xl font-extrabold tracking-tight">
          Everything you were about to ask.
        </h2>
      </motion.div>
      <motion.div {...reveal(0.05)} className="mt-12">
        <Accordion type="single" collapsible className="space-y-3">
          {FAQS.map((f, i) => (
            <AccordionItem key={i} value={`item-${i}`}
              className="rounded-2xl border border-border/60 bg-card/50 backdrop-blur-xl px-5 sm:px-6 gradient-border">
              <AccordionTrigger className="py-5 text-left text-base font-semibold hover:no-underline">
                {f.q}
              </AccordionTrigger>
              <AccordionContent className="pb-5 text-sm text-muted-foreground leading-relaxed">
                {f.a}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </motion.div>
    </div>
  </section>
);

/* ================= CTA banner ================= */

export const CTABanner = () => (
  <section id="contact" className="relative py-20 sm:py-28" data-testid="landing-cta-banner">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10">
      <motion.div {...reveal()} className="relative overflow-hidden rounded-3xl border border-primary/30 bg-gradient-to-br from-primary/15 via-[hsl(var(--info))]/10 to-transparent p-10 sm:p-14 text-center">
        <div className="absolute -top-24 -left-16 h-64 w-64 rounded-full blur-3xl opacity-70 animate-aurora"
          style={{ background: "radial-gradient(circle, hsl(var(--primary) / 0.6), transparent 70%)" }} />
        <div className="absolute -bottom-24 -right-16 h-64 w-64 rounded-full blur-3xl opacity-70 animate-aurora"
          style={{ background: "radial-gradient(circle, hsl(var(--info) / 0.5), transparent 70%)", animationDelay: "-6s" }} />
        <div className="relative">
          <h3 className="text-3xl sm:text-5xl font-extrabold tracking-tight">
            Ready to see your fleet come alive?
          </h3>
          <p className="mt-4 text-muted-foreground max-w-xl mx-auto">
            Deploy the agent, watch the twins fill in, and never look at a spreadsheet again.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link to="/signup" data-testid="cta-banner-signup">
              <Button size="lg" className="h-12 px-6 rounded-xl bg-gradient-to-r from-primary to-[hsl(var(--info))] text-white border-0 shadow-[0_16px_50px_-14px_hsl(var(--primary)/0.75)]">
                Start Free Trial <ArrowRight className="h-4 w-4 ml-1.5" />
              </Button>
            </Link>
            <a href="#pricing" data-testid="cta-banner-pricing">
              <Button size="lg" variant="outline" className="h-12 px-6 rounded-xl border-border/70 bg-background/40 backdrop-blur">
                View pricing
              </Button>
            </a>
          </div>
        </div>
      </motion.div>
    </div>
  </section>
);

/* ================= Footer ================= */

export const LandingFooter = () => (
  <footer id="docs" className="relative border-t border-border/60 bg-background/60 backdrop-blur-xl" data-testid="landing-footer">
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10 py-14 grid gap-10 md:grid-cols-6">
      <div className="md:col-span-2">
        <div className="flex items-center gap-2.5">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-primary to-[hsl(var(--info))] shadow-[0_10px_30px_-8px_hsl(var(--primary)/0.55)] flex items-center justify-center">
            <Cpu className="h-4 w-4 text-white" strokeWidth={2.4} />
          </div>
          <div>
            <div className="text-sm font-bold">Digital Twin</div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Enterprise Cloud</div>
          </div>
        </div>
        <div className="mt-4 text-sm text-muted-foreground max-w-xs leading-relaxed">
          The command center for every computer you manage — live twins, AI predictions, RBAC-safe remediation.
        </div>
        <div className="mt-6 flex gap-2">
          <a href="#" className="h-9 w-9 rounded-lg border border-border/70 flex items-center justify-center hover:bg-foreground/[0.04]"><Github className="h-4 w-4" /></a>
          <a href="#" className="h-9 w-9 rounded-lg border border-border/70 flex items-center justify-center hover:bg-foreground/[0.04]"><Twitter className="h-4 w-4" /></a>
          <a href="#" className="h-9 w-9 rounded-lg border border-border/70 flex items-center justify-center hover:bg-foreground/[0.04]"><Linkedin className="h-4 w-4" /></a>
          <a href="mailto:hello@digitaltwin.io" className="h-9 w-9 rounded-lg border border-border/70 flex items-center justify-center hover:bg-foreground/[0.04]"><Mail className="h-4 w-4" /></a>
        </div>
      </div>

      {[
        { t: "Product", l: ["Features", "Pricing", "Changelog", "Roadmap"] },
        { t: "Resources", l: ["Documentation", "API Reference", "Blog", "Status"] },
        { t: "Company", l: ["About", "Careers", "Contact", "Security"] },
        { t: "Legal", l: ["Privacy", "Terms", "DPA", "Compliance"] },
      ].map((col) => (
        <div key={col.t}>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{col.t}</div>
          <ul className="mt-4 space-y-2.5 text-sm">
            {col.l.map((x) => (
              <li key={x}><a href="#" className="text-foreground/80 hover:text-foreground transition-colors">{x}</a></li>
            ))}
          </ul>
        </div>
      ))}
    </div>

    <div className="border-t border-border/60">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-10 py-6 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
        <div>© {new Date().getFullYear()} Digital Twin Platform · All rights reserved.</div>
        <div className="ml-auto flex items-center gap-4">
          <span className="inline-flex items-center gap-1.5"><MapPin className="h-3 w-3" /> San Francisco · Bangalore</span>
          <span className="inline-flex items-center gap-1.5"><Server className="h-3 w-3" /> Region: US-West</span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse-dot" /> All systems operational
          </span>
        </div>
      </div>
    </div>
  </footer>
);
