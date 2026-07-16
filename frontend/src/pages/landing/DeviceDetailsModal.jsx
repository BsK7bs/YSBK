import React, { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  X, Cpu, MemoryStick, Thermometer, HardDrive, Wifi, HeartPulse,
  Radio, Clock, Terminal, ChevronRight, ShieldCheck,
} from "lucide-react";

const TONE_LABELS = ["CPU 42%", "TEMP 63°C", "RAM 61%", "HEALTH 94", "SSD OK", "NET 1G", "GPU 38%", "PWR 45W"];

/**
 * Live "device details" modal for the 3D hero scene.
 *
 * Connects to `wss://.../api/ws/demo/{nodeId}` — a public FastAPI WebSocket
 * that streams deterministic synthetic telemetry at ~1 Hz. No auth needed.
 * Falls back to a local simulator if the socket cannot be established.
 */
export default function DeviceDetailsModal({ open, nodeId, nodeIndex = 0, onClose }) {
  const [data, setData] = useState(null);
  const [connected, setConnected] = useState(false);
  const [history, setHistory] = useState([]); // cpu series for sparkline
  const wsRef = useRef(null);
  const simRef = useRef(null);

  // Connect to demo WebSocket when modal opens
  useEffect(() => {
    if (!open || !nodeId) return;

    setData(null);
    setConnected(false);
    setHistory([]);

    const backendUrl = process.env.REACT_APP_BACKEND_URL || window.location.origin;
    const wsUrl = backendUrl.replace(/^http/, "ws") + `/api/ws/demo/${encodeURIComponent(nodeId)}`;

    let ws;
    try {
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          setData(msg);
          setHistory((h) => {
            const next = [...h, msg.metrics?.cpu_pct ?? 0];
            return next.slice(-40);
          });
        } catch {}
      };
      ws.onerror = () => startSim();
      ws.onclose = () => setConnected(false);
    } catch {
      startSim();
    }

    function startSim() {
      // Local fallback simulator so the modal is always populated
      let tick = 0;
      const seed = (nodeId || "").split("").reduce((a, c) => a + c.charCodeAt(0), 0);
      const rand = (a, b) => a + ((Math.sin(seed + tick) + 1) / 2) * (b - a);
      simRef.current = setInterval(() => {
        tick += 1;
        const cpu = Math.max(3, Math.min(99, 40 + Math.sin(tick / 6) * 15 + Math.random() * 5));
        const ram = Math.max(20, Math.min(96, 60 + Math.cos(tick / 8) * 6 + Math.random() * 2));
        const temp = Math.max(35, Math.min(95, 62 + Math.sin(tick / 5) * 8 + Math.random() * 1.5));
        const msg = {
          type: "telemetry",
          hostname: `LAB-PC-${(seed % 90 + 10)}`,
          os: "Windows 11 Pro",
          cpu_model: "Intel Core i7-13700",
          ram_gb: 32,
          uptime_days: 7 + (seed % 30),
          disk_used_pct: 52,
          metrics: {
            cpu_pct: Math.round(cpu * 10) / 10,
            ram_pct: Math.round(ram * 10) / 10,
            temp_c: Math.round(temp * 10) / 10,
            net_rx_kbps: Math.round(rand(20, 300)),
            net_tx_kbps: Math.round(rand(10, 200)),
            health_score: 92 + Math.round(Math.sin(tick / 10) * 3),
          },
          recent_events: tick % 12 === 0 ? [{ severity: "info", text: "SMART self-test passed" }] : [],
          tick,
        };
        setData(msg);
        setHistory((h) => [...h, msg.metrics.cpu_pct].slice(-40));
      }, 1000);
    }

    return () => {
      try { ws?.close(); } catch {}
      if (simRef.current) clearInterval(simRef.current);
      wsRef.current = null;
      simRef.current = null;
    };
  }, [open, nodeId]);

  // ESC to close
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose?.(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const m = data?.metrics;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[100] flex items-center justify-center pointer-events-auto"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          data-testid="device-details-modal"
        >
          {/* backdrop */}
          <div className="absolute inset-0 bg-black/60 backdrop-blur-md" onClick={onClose} />

          {/* card */}
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.94 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.94 }}
            transition={{ type: "spring", stiffness: 260, damping: 26 }}
            className="relative w-[92%] max-w-[560px] rounded-2xl border border-cyan-400/25 bg-[#080f1e]/95 backdrop-blur-xl shadow-[0_40px_120px_-30px_rgba(34,165,255,0.5)] overflow-hidden"
          >
            {/* Corner glow */}
            <div className="pointer-events-none absolute -top-24 -right-24 h-56 w-56 rounded-full blur-3xl opacity-60"
              style={{ background: "radial-gradient(circle, #22a5ff, transparent 70%)" }} />
            <div className="pointer-events-none absolute -bottom-24 -left-24 h-56 w-56 rounded-full blur-3xl opacity-40"
              style={{ background: "radial-gradient(circle, #4dd0e1, transparent 70%)" }} />

            {/* Header */}
            <div className="relative flex items-center gap-3 px-5 py-4 border-b border-cyan-400/15">
              <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-[0_10px_30px_-8px_rgba(34,165,255,0.7)]">
                <Radio className="h-4 w-4 text-white" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <div className="text-sm font-bold tracking-tight text-white truncate" data-testid="device-modal-hostname">
                    {data?.hostname || "Connecting…"}
                  </div>
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 text-emerald-300 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-widest">
                    <span className="relative flex h-1.5 w-1.5">
                      <span className="absolute inset-0 rounded-full bg-emerald-400 animate-ping" />
                      <span className="relative h-1.5 w-1.5 rounded-full bg-emerald-400" />
                    </span>
                    {connected ? "Live · WS" : "Live · Sim"}
                  </span>
                </div>
                <div className="text-[10px] text-cyan-300/60 font-mono truncate">
                  {data?.os || "-"} · {data?.cpu_model || "-"} · {data?.ram_gb || "-"}GB RAM
                </div>
              </div>
              <button
                onClick={onClose}
                className="h-8 w-8 rounded-lg border border-cyan-400/20 text-cyan-300/70 hover:text-white hover:bg-white/5 flex items-center justify-center transition"
                aria-label="Close details"
                data-testid="device-modal-close"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Body */}
            <div className="relative p-5 grid grid-cols-4 gap-3">
              <Metric icon={Cpu}         label="CPU"     value={m?.cpu_pct}    unit="%"   color="#22a5ff" />
              <Metric icon={MemoryStick} label="RAM"     value={m?.ram_pct}    unit="%"   color="#4dd0e1" />
              <Metric icon={Thermometer} label="Temp"    value={m?.temp_c}     unit="°C"  color="#f59e0b" />
              <Metric icon={HeartPulse}  label="Health"  value={m?.health_score} unit=""  color="#4ade80" ring />

              {/* Sparkline */}
              <div className="col-span-4 rounded-xl border border-cyan-400/15 bg-black/40 p-3">
                <div className="flex items-center justify-between mb-1">
                  <div className="text-[9px] uppercase tracking-widest text-cyan-300/60 font-mono">CPU · last 40s</div>
                  <div className="text-[10px] text-cyan-300 font-mono tabular-nums">
                    tick #{data?.tick ?? 0}
                  </div>
                </div>
                <Sparkline data={history} />
              </div>

              {/* Bottom info row */}
              <InfoTile icon={HardDrive} label="Disk used" value={data ? `${data.disk_used_pct}%` : "—"} />
              <InfoTile icon={Wifi}      label="Net RX"    value={m ? `${m.net_rx_kbps} kbps` : "—"} />
              <InfoTile icon={Wifi}      label="Net TX"    value={m ? `${m.net_tx_kbps} kbps` : "—"} />
              <InfoTile icon={Clock}     label="Uptime"    value={data ? `${data.uptime_days}d` : "—"} />
            </div>

            {/* Footer actions */}
            <div className="relative border-t border-cyan-400/15 px-5 py-3 flex items-center gap-2">
              <a
                href="/signup"
                className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-[0_10px_30px_-10px_rgba(34,165,255,0.7)]"
                data-testid="device-modal-remote-cta"
              >
                <Terminal className="h-3.5 w-3.5" />
                Run remote command
              </a>
              <a
                href="/signup"
                className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-lg text-xs font-semibold text-cyan-200 border border-cyan-400/20 hover:bg-white/5"
                data-testid="device-modal-open-cta"
              >
                Open full twin <ChevronRight className="h-3.5 w-3.5" />
              </a>
              <div className="ml-auto inline-flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-cyan-300/50 font-mono">
                <ShieldCheck className="h-3 w-3" /> Demo · read-only
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ---------- Sub-components ---------- */

function Metric({ icon: Icon, label, value, unit, color, ring }) {
  const shown = value == null ? "—" : (Math.round(value * 10) / 10).toString();
  return (
    <div className="rounded-xl border border-cyan-400/15 bg-black/40 p-3 relative overflow-hidden">
      <div className="flex items-center justify-between">
        <div className="text-[9px] uppercase tracking-widest text-cyan-300/60 font-mono">{label}</div>
        <Icon className="h-3.5 w-3.5" style={{ color }} />
      </div>
      <div className="mt-2 flex items-baseline gap-0.5">
        <span className="text-2xl font-extrabold tabular-nums text-white leading-none" style={{ textShadow: `0 0 12px ${color}55` }}>
          {shown}
        </span>
        <span className="text-[10px] text-cyan-300/70 ml-0.5">{unit}</span>
      </div>
      {!ring && (
        <div className="mt-2 h-1 rounded-full bg-white/[0.06] overflow-hidden">
          <motion.div
            animate={{ width: `${Math.min(100, value || 0)}%` }}
            transition={{ duration: 0.6 }}
            className="h-full rounded-full"
            style={{ background: `linear-gradient(90deg, ${color}, #22a5ff)` }}
          />
        </div>
      )}
      {ring && (
        <div className="mt-1.5 text-[10px] text-emerald-300/80 font-mono">
          {value >= 90 ? "EXCELLENT" : value >= 75 ? "GOOD" : value >= 55 ? "FAIR" : "POOR"}
        </div>
      )}
    </div>
  );
}

function InfoTile({ icon: Icon, label, value }) {
  return (
    <div className="rounded-lg border border-cyan-400/10 bg-black/30 px-3 py-2 flex items-center gap-2">
      <Icon className="h-3.5 w-3.5 text-cyan-300/70" />
      <div className="min-w-0">
        <div className="text-[8px] uppercase tracking-widest text-cyan-300/50 font-mono">{label}</div>
        <div className="text-[11px] text-white truncate tabular-nums font-mono">{value}</div>
      </div>
    </div>
  );
}

function Sparkline({ data }) {
  if (!data || data.length < 2) {
    return <div className="h-14 flex items-center justify-center text-[10px] text-cyan-300/40 font-mono">waiting for stream…</div>;
  }
  const w = 480, h = 56;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = Math.max(1, max - min);
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 6) - 3;
    return `${x},${y}`;
  });
  const areaPath = `M 0 ${h} L ${pts.join(" L ")} L ${w} ${h} Z`;
  const linePath = `M ${pts.join(" L ")}`;
  const last = data[data.length - 1];
  const lastX = w;
  const lastY = h - ((last - min) / range) * (h - 6) - 3;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-14" preserveAspectRatio="none">
      <defs>
        <linearGradient id="cpu-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#22a5ff" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#22a5ff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#cpu-area)" />
      <path d={linePath} fill="none" stroke="#4dd0e1" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lastX} cy={lastY} r="2.5" fill="#4dd0e1" />
      <circle cx={lastX} cy={lastY} r="5" fill="#4dd0e1" opacity="0.3" />
    </svg>
  );
}
