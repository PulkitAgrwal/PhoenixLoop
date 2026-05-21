"use client";

import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  TooltipProps,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ExperimentRecord } from "@/lib/types";

interface EvalBarChartProps {
  experiment: ExperimentRecord;
}

interface ChartDataPoint {
  metric: string;
  baseline: number | null;
  candidate: number | null;
  lowerIsBetter: boolean;
}

const MAX_LATENCY_MS = 5000; // for normalization

function normalizeValue(
  value: number | null,
  isLatency: boolean
): number | null {
  if (value == null) return null;
  if (isLatency) {
    // Normalize latency: cap at MAX_LATENCY_MS, then invert so lower = shorter bar? No — we display normalized as 0-100 where 0 is best (shortest latency)
    // For grouped bar chart, we just normalize to 0-100 range directly, not invert visually
    return Math.min((value / MAX_LATENCY_MS) * 100, 100);
  }
  // Rates are already 0-1; convert to percentage
  return value * 100;
}

function buildChartData(experiment: ExperimentRecord): ChartDataPoint[] {
  return [
    {
      metric: "Release Score",
      baseline:
        experiment.baseline_release_score != null
          ? experiment.baseline_release_score * 100
          : null,
      candidate:
        experiment.candidate_release_score != null
          ? experiment.candidate_release_score * 100
          : null,
      lowerIsBetter: false,
    },
    {
      metric: "Critical Fail %",
      baseline:
        experiment.baseline_critical_failure_rate != null
          ? experiment.baseline_critical_failure_rate * 100
          : null,
      candidate:
        experiment.candidate_critical_failure_rate != null
          ? experiment.candidate_critical_failure_rate * 100
          : null,
      lowerIsBetter: true,
    },
    {
      metric: "Latency P50",
      baseline: normalizeValue(
        experiment.baseline_latency_p50_ms,
        true
      ),
      candidate: normalizeValue(
        experiment.candidate_latency_p50_ms,
        true
      ),
      lowerIsBetter: true,
    },
    {
      metric: "Hallucination %",
      baseline:
        experiment.baseline_hallucination_rate != null
          ? experiment.baseline_hallucination_rate * 100
          : null,
      candidate:
        experiment.candidate_hallucination_rate != null
          ? experiment.candidate_hallucination_rate * 100
          : null,
      lowerIsBetter: true,
    },
    {
      metric: "Regression Pass %",
      baseline: null,
      candidate:
        experiment.regression_cases_pass_rate != null
          ? experiment.regression_cases_pass_rate * 100
          : null,
      lowerIsBetter: false,
    },
    {
      metric: "Safety Pass %",
      baseline: null,
      candidate:
        experiment.safety_canary_pass_rate != null
          ? experiment.safety_canary_pass_rate * 100
          : null,
      lowerIsBetter: false,
    },
  ];
}

interface CustomTooltipPayloadItem {
  name: string;
  value: number | null;
  color: string;
}

function CustomTooltip({
  active,
  payload,
  label,
}: TooltipProps<number, string> & {
  payload?: CustomTooltipPayloadItem[];
}) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-popover-foreground shadow-md">
      <p className="mb-1.5 text-xs font-semibold">{label}</p>
      {payload.map((entry) => (
        <div
          key={entry.name}
          className="flex items-center gap-2 text-xs"
        >
          <span
            className="inline-block h-2 w-2 rounded-sm shrink-0"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-muted-foreground">{entry.name}:</span>
          <span className="font-medium tabular-nums">
            {entry.value != null ? `${entry.value.toFixed(1)}` : "—"}
          </span>
        </div>
      ))}
    </div>
  );
}

export function EvalBarChart({ experiment }: EvalBarChartProps) {
  const data = buildChartData(experiment);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold">
          Metrics Comparison
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Latency normalized to 0–100 (0 = fastest). Rates as percentage.
        </p>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart
            data={data}
            margin={{ top: 4, right: 12, bottom: 4, left: 0 }}
            barCategoryGap="25%"
            barGap={3}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              vertical={false}
              className="stroke-border"
            />
            <XAxis
              dataKey="metric"
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
              axisLine={false}
              tickLine={false}
              width={28}
            />
            <Tooltip
              content={<CustomTooltip />}
              cursor={{ fill: "hsl(var(--muted))", opacity: 0.5 }}
            />
            <Legend
              wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }}
              iconType="square"
            />
            <Bar
              dataKey="baseline"
              name="Baseline"
              fill="#94a3b8"
              radius={[3, 3, 0, 0]}
              maxBarSize={40}
            />
            <Bar
              dataKey="candidate"
              name="Candidate"
              fill="#10b981"
              radius={[3, 3, 0, 0]}
              maxBarSize={40}
            />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
