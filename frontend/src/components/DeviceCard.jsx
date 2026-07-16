import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { formatRelative } from "../lib/format";
import { OnlineBadge, RiskBadge } from "./StatBadge";
import { HealthGauge } from "./HealthGauge";
import { Cpu, MemoryStick, Thermometer, Wifi } from "lucide-react";
import { cn } from "../lib/utils";

function Metric({ icon: Icon, label, value, unit, testId }) {
  return (
    <div className="rounded-xl bg-foreground/[0.03] border border-border p-3" data-testid={testId}>
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <div className="mt-1 text-sm font-medium tabular-nums">
        {value == null ? "—" : value}
        {value != null && unit && <span className="text-muted-foreground text-xs ml-1">{unit}</span>}
      </div>
    </div>
  );
}

export function DeviceCard({ device }) {
  const m = device.latest_metrics || {};
  const cpu = m.cpu_percent;
  const ram = m.ram_percent;
  const temp = m.cpu_temp_c;
  const net = m.net_down_kbps || m.net_up_kbps;

  return (
    <Link
      to={`/app/devices/${device.id}`}
      data-testid="device-card"
      className={cn(
        "group relative block rounded-2xl border border-border bg-card p-4 sm:p-5",
        "shadow-[var(--shadow-1)] card-hover",
      )}
    >
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold truncate" data-testid="device-card-name">
              {device.display_name || device.hostname}
            </div>
            <div className="text-xs text-muted-foreground truncate">
              {device.os_name || "Unknown OS"} {device.os_version || ""} · {device.hostname}
            </div>
            <div className="mt-2 flex items-center gap-2 flex-wrap">
              <OnlineBadge online={device.is_online} />
              <RiskBadge risk={device.is_online ? device.risk_level : "offline"} />
            </div>
          </div>
          <HealthGauge score={device.health_score} size={72} thickness={8} showLabel={false} />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3">
          <Metric icon={Cpu} label="CPU" value={cpu != null ? cpu.toFixed(0) : null} unit="%" testId="device-metric-cpu" />
          <Metric icon={MemoryStick} label="RAM" value={ram != null ? ram.toFixed(0) : null} unit="%" testId="device-metric-ram" />
          <Metric icon={Thermometer} label="Temp" value={temp != null ? temp.toFixed(0) : null} unit="°C" testId="device-metric-temp" />
          <Metric icon={Wifi} label="Network" value={net != null ? Math.round(net) : null} unit="kbps" testId="device-metric-net" />
        </div>

        <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
          <span>Last seen {formatRelative(device.last_seen)}</span>
          <span className="opacity-0 group-hover:opacity-100 transition-opacity text-primary">View twin →</span>
        </div>
      </motion.div>
    </Link>
  );
}
