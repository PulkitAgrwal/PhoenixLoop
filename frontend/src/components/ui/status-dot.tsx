import * as React from "react";
import { cn } from "@/lib/utils";

export type StatusTone = "brand" | "fail" | "warn" | "mute" | "ink";

const toneClass: Record<StatusTone, string> = {
  brand: "bg-brand",
  fail: "bg-fail",
  warn: "bg-warn",
  mute: "bg-mute",
  ink: "bg-ink",
};

export interface StatusDotProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: StatusTone;
  pulse?: boolean;
  size?: "xs" | "sm" | "md";
}

export function StatusDot({
  tone = "brand",
  pulse = false,
  size = "sm",
  className,
  ...rest
}: StatusDotProps) {
  const sizeClass = size === "xs" ? "h-1.5 w-1.5" : size === "md" ? "h-3 w-3" : "h-2 w-2";
  return (
    <span
      aria-hidden="true"
      className={cn(
        "relative inline-flex shrink-0 rounded-pill",
        sizeClass,
        toneClass[tone],
        className
      )}
      {...rest}
    >
      {pulse && (
        <span
          className={cn(
            "absolute inset-0 rounded-pill animate-pulse-dot",
            toneClass[tone],
            "opacity-50"
          )}
        />
      )}
    </span>
  );
}
