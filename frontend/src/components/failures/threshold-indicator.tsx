"use client";

import React from "react";
import { cn } from "@/lib/utils";

interface ThresholdIndicatorProps {
  current: number;
  threshold: number;
  label: string;
}

export function ThresholdIndicator({
  current,
  threshold,
  label,
}: ThresholdIndicatorProps) {
  const percentage = threshold > 0 ? Math.min((current / threshold) * 100, 100) : 0;
  const isAbove = current >= threshold;
  const isApproaching = !isAbove && percentage >= 75;

  const barColor = isAbove
    ? "bg-red-500"
    : isApproaching
    ? "bg-amber-500"
    : "bg-green-500";

  const textColor = isAbove
    ? "text-red-600 dark:text-red-400"
    : isApproaching
    ? "text-amber-600 dark:text-amber-400"
    : "text-green-600 dark:text-green-400";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className={cn("font-semibold tabular-nums", textColor)}>
          {current} / {threshold}
        </span>
      </div>
      <div className="relative h-2 w-full overflow-hidden rounded-full bg-secondary">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            barColor
          )}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}
