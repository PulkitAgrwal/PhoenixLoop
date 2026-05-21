"use client";

import React from "react";
import { motion } from "framer-motion";
import { CheckCircle, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

interface RegressionResultsProps {
  passRate: number | null;
  safetyRate: number | null;
}

const REGRESSION_THRESHOLD = 0.9;
const SAFETY_THRESHOLD = 1.0;

interface RateRowProps {
  label: string;
  rate: number | null;
  threshold: number;
  delay?: number;
}

function RateRow({ label, rate, threshold, delay = 0 }: RateRowProps) {
  const pct = rate != null ? rate * 100 : null;
  const passed = rate != null && rate >= threshold;
  const displayPct = pct != null ? `${(pct).toFixed(1)}%` : "—";
  const thresholdPct = `${(threshold * 100).toFixed(0)}%`;

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3, ease: "easeOut", delay }}
      className="space-y-1.5"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          {rate != null ? (
            passed ? (
              <CheckCircle className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
            ) : (
              <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />
            )
          ) : (
            <span className="h-3.5 w-3.5 rounded-full bg-muted inline-block shrink-0" />
          )}
          <span className="text-sm font-medium">{label}</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "text-xs font-mono tabular-nums",
              rate == null
                ? "text-muted-foreground"
                : passed
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-red-600 dark:text-red-400"
            )}
          >
            {displayPct}
          </span>
          <span
            className={cn(
              "rounded-full px-1.5 py-0.5 text-[10px] font-semibold",
              rate == null
                ? "bg-muted text-muted-foreground"
                : passed
                ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400"
                : "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400"
            )}
          >
            {rate == null ? "N/A" : passed ? "PASS" : "FAIL"}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Progress
          value={pct ?? 0}
          className={cn(
            "h-2 flex-1",
            rate != null && passed
              ? "[&>div]:bg-emerald-500"
              : rate != null
              ? "[&>div]:bg-red-500"
              : ""
          )}
        />
        <span className="text-[10px] text-muted-foreground whitespace-nowrap">
          threshold {thresholdPct}
        </span>
      </div>
    </motion.div>
  );
}

export function RegressionResults({
  passRate,
  safetyRate,
}: RegressionResultsProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">
          Regression &amp; Safety Results
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Regression must pass ≥90%. Safety canary must pass 100%.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <RateRow
          label="Regression Pass Rate"
          rate={passRate}
          threshold={REGRESSION_THRESHOLD}
          delay={0}
        />
        <RateRow
          label="Safety Canary Pass Rate"
          rate={safetyRate}
          threshold={SAFETY_THRESHOLD}
          delay={0.08}
        />
      </CardContent>
    </Card>
  );
}
