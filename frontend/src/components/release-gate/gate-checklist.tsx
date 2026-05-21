"use client";

import React from "react";
import { motion } from "framer-motion";
import { CheckCircle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface GateChecklistProps {
  rulesDetail: Record<string, unknown> | null;
}

interface RuleConfig {
  key: string;
  label: string;
  description: string;
  formatActual: (actual: unknown, baseline?: unknown) => string;
  formatThreshold: (threshold: unknown, baseline?: unknown) => string;
}

const RULE_CONFIGS: RuleConfig[] = [
  {
    key: "score_delta",
    label: "Score Delta",
    description: "Candidate score improvement ≥ 0.05 over baseline",
    formatActual: (actual) =>
      typeof actual === "number" ? `+${actual.toFixed(3)}` : "—",
    formatThreshold: (threshold) =>
      typeof threshold === "number" ? `≥ ${threshold.toFixed(3)}` : "—",
  },
  {
    key: "critical_failure",
    label: "Critical Failure Rate",
    description: "Critical failure rate must be zero",
    formatActual: (actual) =>
      typeof actual === "number" ? `${(actual * 100).toFixed(1)}%` : "—",
    formatThreshold: (threshold) =>
      typeof threshold === "number" ? `= ${(threshold * 100).toFixed(1)}%` : "—",
  },
  {
    key: "hallucination",
    label: "Hallucination Rate",
    description: "Hallucination rate ≤ baseline",
    formatActual: (actual, baseline) => {
      const a = typeof actual === "number" ? `${(actual * 100).toFixed(1)}%` : "—";
      const b = typeof baseline === "number" ? ` (baseline: ${(baseline * 100).toFixed(1)}%)` : "";
      return `${a}${b}`;
    },
    formatThreshold: (threshold) =>
      typeof threshold === "number" ? `≤ ${(threshold * 100).toFixed(1)}%` : "—",
  },
  {
    key: "latency",
    label: "Latency",
    description: "Latency ≤ 120% of baseline",
    formatActual: (actual, baseline) => {
      const a = typeof actual === "number" ? `${actual.toFixed(0)} ms` : "—";
      const b = typeof baseline === "number" ? ` (baseline: ${baseline.toFixed(0)} ms)` : "";
      return `${a}${b}`;
    },
    formatThreshold: (threshold) =>
      typeof threshold === "number" ? `≤ ${threshold.toFixed(0)} ms` : "—",
  },
  {
    key: "regression",
    label: "Regression Pass Rate",
    description: "Regression test pass rate ≥ 90%",
    formatActual: (actual) =>
      typeof actual === "number" ? `${(actual * 100).toFixed(1)}%` : "—",
    formatThreshold: (threshold) =>
      typeof threshold === "number" ? `≥ ${(threshold * 100).toFixed(1)}%` : "—",
  },
  {
    key: "safety_canary",
    label: "Safety Canary",
    description: "Safety canary pass rate = 100%",
    formatActual: (actual) =>
      typeof actual === "number" ? `${(actual * 100).toFixed(1)}%` : "—",
    formatThreshold: (threshold) =>
      typeof threshold === "number" ? `= ${(threshold * 100).toFixed(1)}%` : "—",
  },
];

interface RuleData {
  passed: boolean;
  actual: unknown;
  threshold: unknown;
  baseline?: unknown;
}

function extractRuleData(
  rulesDetail: Record<string, unknown> | null,
  key: string
): RuleData | null {
  if (!rulesDetail) return null;
  const raw = rulesDetail[key];
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  return {
    passed: Boolean(r["passed"]),
    actual: r["actual"],
    threshold: r["threshold"],
    baseline: r["baseline"],
  };
}

const rowVariants = {
  hidden: { opacity: 0, x: -12 },
  visible: (i: number) => ({
    opacity: 1,
    x: 0,
    transition: {
      duration: 0.3,
      ease: "easeOut",
      delay: i * 0.1,
    },
  }),
};

const iconVariants = {
  hidden: { scale: 0, rotate: -45 },
  visible: {
    scale: 1,
    rotate: 0,
    transition: {
      type: "spring" as const,
      stiffness: 400,
      damping: 15,
    },
  },
};

export function GateChecklist({ rulesDetail }: GateChecklistProps) {
  return (
    <div className="space-y-2">
      {RULE_CONFIGS.map((rule, index) => {
        const data = extractRuleData(rulesDetail, rule.key);
        const passed = data?.passed ?? null;

        return (
          <motion.div
            key={rule.key}
            custom={index}
            initial="hidden"
            animate="visible"
            variants={rowVariants}
            className={cn(
              "flex items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors",
              passed === true &&
                "border-green-200 bg-green-50/50 dark:border-green-800 dark:bg-green-950/20",
              passed === false &&
                "border-red-200 bg-red-50/50 dark:border-red-800 dark:bg-red-950/20",
              passed === null &&
                "border-border bg-muted/20"
            )}
          >
            {/* Icon */}
            <motion.div
              custom={index}
              initial="hidden"
              animate="visible"
              variants={iconVariants}
              className="mt-0.5 shrink-0"
            >
              {passed === true ? (
                <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400" />
              ) : passed === false ? (
                <XCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
              ) : (
                <div className="h-4 w-4 rounded-full border-2 border-muted-foreground/30" />
              )}
            </motion.div>

            {/* Content */}
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center justify-between gap-1">
                <span
                  className={cn(
                    "text-sm font-medium",
                    passed === true && "text-green-700 dark:text-green-300",
                    passed === false && "text-red-700 dark:text-red-300",
                    passed === null && "text-foreground"
                  )}
                >
                  {rule.label}
                </span>
                {data && (
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-muted-foreground">
                      Actual:{" "}
                      <span className="font-mono font-medium text-foreground">
                        {rule.formatActual(data.actual, data.baseline)}
                      </span>
                    </span>
                    <span className="text-muted-foreground/60">·</span>
                    <span className="text-muted-foreground">
                      Target:{" "}
                      <span className="font-mono font-medium text-foreground">
                        {rule.formatThreshold(data.threshold, data.baseline)}
                      </span>
                    </span>
                  </div>
                )}
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {rule.description}
              </p>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
