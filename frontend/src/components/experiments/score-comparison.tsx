"use client";

import * as React from "react";
import { TrendingUp, TrendingDown } from "lucide-react";

import { Eyebrow } from "@/components/ui/eyebrow";
import { cn } from "@/lib/utils";
import type { ExperimentRecord } from "@/lib/types";

interface ScoreComparisonProps {
  experiment: ExperimentRecord;
}

type Direction = "higher" | "lower";

interface MetricSpec {
  label: string;
  baseline: number | null;
  candidate: number | null;
  unit: "score" | "pct" | "ms" | "raw";
  direction: Direction;
  notSampledHint?: string;
}

function fmt(value: number | null, unit: MetricSpec["unit"]): string {
  if (value === null) return "—";
  if (unit === "score") return value.toFixed(2);
  if (unit === "pct") return `${(value * 100).toFixed(1)}%`;
  if (unit === "ms") return `${value.toFixed(0)} ms`;
  return value.toFixed(2);
}

function deltaPercent(base: number | null, cand: number | null): string | null {
  if (base === null || cand === null) return null;
  if (base === 0) return cand === 0 ? "—" : null;
  const delta = ((cand - base) / Math.abs(base)) * 100;
  return `${delta >= 0 ? "+" : ""}${delta.toFixed(0)}%`;
}

function deltaIsImprovement(spec: MetricSpec): boolean | null {
  if (spec.baseline === null || spec.candidate === null) return null;
  if (spec.baseline === spec.candidate) return null;
  if (spec.direction === "higher") return spec.candidate > spec.baseline;
  return spec.candidate < spec.baseline;
}

function bar(value: number | null, scale: number = 1): string {
  // Returns a 10-char block bar
  if (value === null) return " ".repeat(10);
  const normalized = Math.max(0, Math.min(1, value / scale));
  const filled = Math.round(normalized * 10);
  return "▆".repeat(filled) + "░".repeat(10 - filled);
}

export function ScoreComparison({ experiment }: ScoreComparisonProps) {
  const metrics: MetricSpec[] = [
    {
      label: "Release score",
      baseline: experiment.baseline_release_score,
      candidate: experiment.candidate_release_score,
      unit: "score",
      direction: "higher",
    },
    {
      label: "Critical failure rate",
      baseline: experiment.baseline_critical_failure_rate,
      candidate: experiment.candidate_critical_failure_rate,
      unit: "pct",
      direction: "lower",
    },
    {
      label: "Hallucination rate",
      baseline: experiment.baseline_hallucination_rate,
      candidate: experiment.candidate_hallucination_rate,
      unit: "pct",
      direction: "lower",
      notSampledHint:
        "Not sampled — LLM judges are skipped in the experiment hot path to stay under the Gemini free-tier RPM ceiling. Code evals score this run.",
    },
    {
      label: "Latency p50",
      baseline: experiment.baseline_latency_p50_ms,
      candidate: experiment.candidate_latency_p50_ms,
      unit: "ms",
      direction: "lower",
    },
  ];

  return (
    <section
      aria-label="Score comparison"
      className="rounded-md border border-hairline overflow-hidden"
    >
      <header className="flex items-center justify-between border-b border-hairline bg-canvas-soft px-4 py-2.5">
        <Eyebrow tone="brand">Scoreboard</Eyebrow>
        <span className="font-mono text-caption text-mute">baseline vs candidate</span>
      </header>

      <div className="grid grid-cols-[1.1fr,1fr,1fr,auto] divide-x divide-hairline bg-canvas">
        <Col label="Metric" mute>
          {metrics.map((m) => {
            const notSampled =
              m.notSampledHint &&
              m.baseline === null &&
              m.candidate === null;
            return (
              <Cell
                key={m.label}
                className="text-body-md-strong text-ink-strong"
              >
                <span
                  className={cn(
                    notSampled && "decoration-mute decoration-dotted underline-offset-4 underline cursor-help"
                  )}
                  title={notSampled ? m.notSampledHint : undefined}
                >
                  {m.label}
                </span>
              </Cell>
            );
          })}
        </Col>
        <Col label={`Baseline · ${experiment.baseline_prompt_version}`} mute>
          {metrics.map((m) => (
            <Cell key={m.label}>
              <ScoreBar
                value={m.baseline}
                unit={m.unit}
                tone="mute"
                notSampledHint={m.notSampledHint}
              />
            </Cell>
          ))}
        </Col>
        <Col
          label={`Candidate · ${experiment.candidate_prompt_version}`}
          highlight
        >
          {metrics.map((m) => {
            const better = deltaIsImprovement(m);
            return (
              <Cell key={m.label}>
                <ScoreBar
                  value={m.candidate}
                  unit={m.unit}
                  tone={better === true ? "brand" : better === false ? "fail" : "ink"}
                  notSampledHint={m.notSampledHint}
                />
              </Cell>
            );
          })}
        </Col>
        <Col label="Δ" mute>
          {metrics.map((m) => {
            const dp = deltaPercent(m.baseline, m.candidate);
            const better = deltaIsImprovement(m);
            return (
              <Cell key={m.label} className="font-mono text-body-sm text-mute">
                {dp ? (
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 px-2 py-0.5",
                      better === true && "text-brand-soft",
                      better === false && "text-fail"
                    )}
                  >
                    {better === true ? (
                      <TrendingUp className="h-3 w-3" aria-hidden />
                    ) : better === false ? (
                      <TrendingDown className="h-3 w-3" aria-hidden />
                    ) : null}
                    {dp}
                  </span>
                ) : (
                  <span className="text-mute">—</span>
                )}
              </Cell>
            );
          })}
        </Col>
      </div>

      <div className="grid grid-cols-2 divide-x divide-hairline border-t border-hairline bg-canvas-soft">
        <RegressionFooter
          label="Regression canaries"
          value={experiment.regression_cases_pass_rate}
        />
        <RegressionFooter
          label="Safety canaries"
          value={experiment.safety_canary_pass_rate}
        />
      </div>
    </section>
  );
}

function Col({
  label,
  children,
  mute,
  highlight,
}: {
  label: string;
  children: React.ReactNode;
  mute?: boolean;
  highlight?: boolean;
}) {
  return (
    <div className={cn("min-w-0", highlight && "bg-canvas-soft/40")}>
      <div
        className={cn(
          "flex h-12 items-center border-b border-hairline px-4 text-eyebrow-mono uppercase",
          mute ? "text-mute" : "text-brand-soft"
        )}
        title={label}
      >
        <span className="truncate min-w-0">{label}</span>
      </div>
      <div>{children}</div>
    </div>
  );
}

function Cell({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "flex h-12 items-center border-b border-hairline px-4 last:border-b-0 text-body-md",
        className
      )}
    >
      {children}
    </div>
  );
}

function ScoreBar({
  value,
  unit,
  tone,
  notSampledHint,
}: {
  value: number | null;
  unit: MetricSpec["unit"];
  tone: "brand" | "fail" | "mute" | "ink";
  notSampledHint?: string;
}) {
  const scale = unit === "pct" ? 1 : unit === "ms" ? 1500 : 1;
  const isNotSampled = value === null && Boolean(notSampledHint);
  return (
    <span
      className="flex items-center gap-3 font-mono text-code"
      title={isNotSampled ? notSampledHint : undefined}
    >
      <span
        className={cn(
          "tracking-tighter select-none",
          tone === "brand" && "text-brand",
          tone === "fail" && "text-fail",
          tone === "mute" && "text-mute",
          tone === "ink" && "text-canvas-text-soft"
        )}
        aria-hidden
      >
        {bar(value, scale)}
      </span>
      <span
        className={cn(
          "num-mono",
          tone === "brand" && "text-brand-soft",
          tone === "fail" && "text-fail",
          tone === "mute" && "text-canvas-text-soft",
          tone === "ink" && "text-canvas-text-soft",
          isNotSampled && "cursor-help"
        )}
      >
        {fmt(value, unit)}
      </span>
    </span>
  );
}

function RegressionFooter({ label, value }: { label: string; value: number | null }) {
  const display = value === null ? "—" : `${Math.round(value * 100)}%`;
  const passed = value !== null && value >= 0.9;
  return (
    <div className="flex items-center justify-between px-5 py-3">
      <span className="text-caption uppercase tracking-eyebrow text-mute">{label}</span>
      <span
        className={cn(
          "num-mono text-body-md",
          passed ? "text-brand-soft" : value === null ? "text-mute" : "text-warn"
        )}
      >
        {display}
      </span>
    </div>
  );
}
