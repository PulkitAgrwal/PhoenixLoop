import * as React from "react";
import { cn } from "@/lib/utils";

export interface MetricNumberProps extends React.HTMLAttributes<HTMLDivElement> {
  value: string | number;
  label?: string;
  suffix?: string;
  tone?: "ink" | "brand" | "fail";
  size?: "sm" | "md" | "lg";
}

export function MetricNumber({
  value,
  label,
  suffix,
  tone = "ink",
  size = "md",
  className,
  ...rest
}: MetricNumberProps) {
  const numClass =
    size === "lg" ? "text-[44px] leading-[44px]" : size === "sm" ? "text-display-sm" : "text-display-md";
  const toneClass =
    tone === "brand" ? "text-brand" : tone === "fail" ? "text-fail" : "text-ink-strong";

  return (
    <div className={cn("flex flex-col gap-1", className)} {...rest}>
      <div className={cn("num-mono font-medium", numClass, toneClass)}>
        {value}
        {suffix && <span className="ml-1 text-body text-body-md font-normal">{suffix}</span>}
      </div>
      {label && (
        <div className="text-caption uppercase tracking-eyebrow text-mute">{label}</div>
      )}
    </div>
  );
}
