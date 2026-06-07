import * as React from "react";
import { cn } from "@/lib/utils";

type StatusVariant = "success" | "error" | "warning" | "info" | "pending";

interface StatusBadgeProps {
  status: StatusVariant;
  label: string;
  pulse?: boolean;
  className?: string;
}

const statusStyles: Record<StatusVariant, string> = {
  success: "border-brand/40 bg-brand/[0.06] text-brand-soft",
  error: "border-fail/40 bg-fail/[0.06] text-fail",
  warning: "border-warn/40 bg-warn/[0.08] text-warn",
  info: "border-hairline bg-canvas-soft text-canvas-text-soft",
  pending: "border-hairline bg-canvas-soft text-mute",
};

const dotStyles: Record<StatusVariant, string> = {
  success: "bg-brand",
  error: "bg-fail",
  warning: "bg-warn",
  info: "bg-canvas-text-soft",
  pending: "bg-mute",
};

export function StatusBadge({
  status,
  label,
  pulse = false,
  className,
}: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-0.5 text-caption-strong font-medium",
        statusStyles[status],
        className
      )}
    >
      {pulse && (
        <span className="relative flex h-2 w-2 shrink-0" aria-hidden>
          <span
            className={cn(
              "absolute inline-flex h-full w-full rounded-pill opacity-60 animate-pulse-dot",
              dotStyles[status]
            )}
          />
          <span className={cn("relative inline-flex h-2 w-2 rounded-pill", dotStyles[status])} />
        </span>
      )}
      {label}
    </span>
  );
}
