import React from "react";
import { Button } from "./ui/button";
import { cn } from "../lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  primaryAction,
  primaryLabel,
  primaryTestId = "empty-state-primary-cta",
  secondary,
  className,
}) {
  return (
    <div
      data-testid="empty-state"
      className={cn(
        "rounded-2xl border border-dashed border-border bg-foreground/[0.02] p-8",
        "flex items-start gap-5",
        className,
      )}
    >
      {Icon && (
        <div className="h-12 w-12 rounded-xl bg-primary/10 border border-primary/25 text-primary flex items-center justify-center shrink-0">
          <Icon className="h-5 w-5" />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="text-base font-semibold">{title}</div>
        {description && <div className="mt-1 text-sm text-muted-foreground max-w-prose">{description}</div>}
        {(primaryAction || secondary) && (
          <div className="mt-5 flex flex-col sm:flex-row gap-3">
            {primaryAction && (
              <Button onClick={primaryAction} data-testid={primaryTestId}>
                {primaryLabel}
              </Button>
            )}
            {secondary}
          </div>
        )}
      </div>
    </div>
  );
}
