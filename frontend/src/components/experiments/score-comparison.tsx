"use client";

import React from "react";
import { motion } from "framer-motion";
import { ArrowRight, TrendingDown, TrendingUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { ExperimentRecord } from "@/lib/types";

interface ScoreComparisonProps {
  experiment: ExperimentRecord;
}

interface MetricRowProps {
  label: string;
  value: number | null;
  formatFn?: (v: number) => string;
  higherIsBetter?: boolean;
  compareValue?: number | null;
}

function MetricRow({
  label,
  value,
  formatFn = (v) => v.toFixed(2),
  higherIsBetter = true,
  compareValue,
}: MetricRowProps) {
  const display = value != null ? formatFn(value) : "—";
  let trendColor = "text-muted-foreground";

  if (value != null && compareValue != null) {
    const better = higherIsBetter ? value > compareValue : value < compareValue;
    trendColor = better ? "text-emerald-600" : "text-red-500";
  }

  return (
    <div className="flex items-center justify-between gap-2 py-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn("text-sm font-medium tabular-nums", trendColor)}>
        {display}
      </span>
    </div>
  );
}

interface SideCardProps {
  label: string;
  promptVersion: string;
  releaseScore: number | null;
  criticalFailureRate: number | null;
  latencyP50Ms: number | null;
  hallucinationRate: number | null;
  compareTo: {
    releaseScore: number | null;
    criticalFailureRate: number | null;
    latencyP50Ms: number | null;
    hallucinationRate: number | null;
  } | null;
  highlight?: "green" | "red" | null;
  delay?: number;
}

function SideCard({
  label,
  promptVersion,
  releaseScore,
  criticalFailureRate,
  latencyP50Ms,
  hallucinationRate,
  compareTo,
  highlight,
  delay = 0,
}: SideCardProps) {
  const scoreDisplay =
    releaseScore != null ? (releaseScore * 100).toFixed(1) : "—";
  const scoreValue = releaseScore != null ? releaseScore * 100 : 0;

  const borderClass =
    highlight === "green"
      ? "border-emerald-300 dark:border-emerald-700"
      : highlight === "red"
      ? "border-red-300 dark:border-red-700"
      : "border-border";

  const bgClass =
    highlight === "green"
      ? "bg-emerald-50/40 dark:bg-emerald-950/20"
      : highlight === "red"
      ? "bg-red-50/40 dark:bg-red-950/20"
      : "";

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut", delay }}
    >
      <Card className={cn("flex flex-col gap-0 h-full", borderClass, bgClass)}>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="text-sm font-semibold">{label}</CardTitle>
            <span className="text-xs font-mono text-muted-foreground truncate max-w-[120px]">
              {promptVersion}
            </span>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {/* Release Score — large display */}
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">Release Score</p>
            <p
              className={cn(
                "text-4xl font-bold tabular-nums leading-none",
                highlight === "green"
                  ? "text-emerald-600 dark:text-emerald-400"
                  : highlight === "red"
                  ? "text-red-500 dark:text-red-400"
                  : "text-foreground"
              )}
            >
              {scoreDisplay}
              {releaseScore != null && (
                <span className="text-lg font-medium text-muted-foreground ml-0.5">
                  /100
                </span>
              )}
            </p>
            <Progress
              value={scoreValue}
              className={cn(
                "h-2",
                highlight === "green"
                  ? "[&>div]:bg-emerald-500"
                  : highlight === "red"
                  ? "[&>div]:bg-red-500"
                  : ""
              )}
            />
          </div>

          {/* Other metrics */}
          <div className="space-y-0.5 border-t pt-3">
            <MetricRow
              label="Critical Failure Rate"
              value={
                criticalFailureRate != null
                  ? criticalFailureRate * 100
                  : null
              }
              formatFn={(v) => `${v.toFixed(1)}%`}
              higherIsBetter={false}
              compareValue={
                compareTo?.criticalFailureRate != null
                  ? compareTo.criticalFailureRate * 100
                  : null
              }
            />
            <MetricRow
              label="Latency P50"
              value={latencyP50Ms}
              formatFn={(v) => `${v.toFixed(0)} ms`}
              higherIsBetter={false}
              compareValue={compareTo?.latencyP50Ms}
            />
            <MetricRow
              label="Hallucination Rate"
              value={
                hallucinationRate != null ? hallucinationRate * 100 : null
              }
              formatFn={(v) => `${v.toFixed(1)}%`}
              higherIsBetter={false}
              compareValue={
                compareTo?.hallucinationRate != null
                  ? compareTo.hallucinationRate * 100
                  : null
              }
            />
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

export function ScoreComparison({ experiment }: ScoreComparisonProps) {
  const baseline = experiment.baseline_release_score;
  const candidate = experiment.candidate_release_score;

  let delta: number | null = null;
  let deltaPositive = false;
  let candidateHighlight: "green" | "red" | null = null;

  if (baseline != null && candidate != null) {
    delta = (candidate - baseline) * 100;
    deltaPositive = delta >= 0;
    candidateHighlight = deltaPositive ? "green" : "red";
  }

  return (
    <div className="space-y-3">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Score Comparison
      </h3>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        {/* Baseline */}
        <SideCard
          label="Baseline"
          promptVersion={experiment.baseline_prompt_version}
          releaseScore={experiment.baseline_release_score}
          criticalFailureRate={experiment.baseline_critical_failure_rate}
          latencyP50Ms={experiment.baseline_latency_p50_ms}
          hallucinationRate={experiment.baseline_hallucination_rate}
          compareTo={null}
          highlight={null}
          delay={0}
        />

        {/* Delta indicator */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.3, delay: 0.2 }}
          className="flex flex-col items-center gap-1.5 px-1"
        >
          <ArrowRight className="h-5 w-5 text-muted-foreground/60" />
          {delta != null && (
            <div
              className={cn(
                "flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-semibold",
                deltaPositive
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400"
                  : "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400"
              )}
            >
              {deltaPositive ? (
                <TrendingUp className="h-3 w-3" />
              ) : (
                <TrendingDown className="h-3 w-3" />
              )}
              {deltaPositive ? "+" : ""}
              {delta.toFixed(1)}
            </div>
          )}
        </motion.div>

        {/* Candidate */}
        <SideCard
          label="Candidate"
          promptVersion={experiment.candidate_prompt_version}
          releaseScore={experiment.candidate_release_score}
          criticalFailureRate={experiment.candidate_critical_failure_rate}
          latencyP50Ms={experiment.candidate_latency_p50_ms}
          hallucinationRate={experiment.candidate_hallucination_rate}
          compareTo={{
            releaseScore: experiment.baseline_release_score,
            criticalFailureRate: experiment.baseline_critical_failure_rate,
            latencyP50Ms: experiment.baseline_latency_p50_ms,
            hallucinationRate: experiment.baseline_hallucination_rate,
          }}
          highlight={candidateHighlight}
          delay={0.08}
        />
      </div>
    </div>
  );
}
