import React from "react";
import { cn } from "../lib/utils";

export function LiveIndicator({ label = "Live", className }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-[11px] uppercase tracking-widest text-emerald-300",
        className,
      )}
    >
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-500 opacity-60 animate-ping" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
      </span>
      {label}
    </span>
  );
}
