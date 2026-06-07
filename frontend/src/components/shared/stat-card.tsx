"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface StatCardProps {
  title: string;
  value: string | number;
  description?: string;
  icon?: React.ReactNode;
  trend?: { value: number; positive: boolean };
  className?: string;
}

export function StatCard({
  title,
  value,
  description,
  icon,
  trend,
  className,
}: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className={cn("", className)}
    >
      <div className="rounded-md border border-hairline bg-canvas p-5">
        <div className="flex items-start justify-between gap-3">
          <p className="text-caption uppercase tracking-eyebrow text-mute">{title}</p>
          {icon && <div className="text-mute">{icon}</div>}
        </div>
        <div className="mt-3 num-mono text-[28px] leading-[32px] text-ink-strong">{value}</div>
        <div className="mt-2 flex items-center gap-2">
          {trend && (
            <span
              className={cn(
                "flex items-center gap-0.5 text-caption font-medium",
                trend.positive ? "text-brand-soft" : "text-fail"
              )}
            >
              {trend.positive ? (
                <TrendingUp className="h-3 w-3" aria-hidden />
              ) : (
                <TrendingDown className="h-3 w-3" aria-hidden />
              )}
              {Math.abs(trend.value)}%
            </span>
          )}
          {description && <p className="text-caption text-body">{description}</p>}
        </div>
      </div>
    </motion.div>
  );
}
