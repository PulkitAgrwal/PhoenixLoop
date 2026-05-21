"use client";

import React, { useMemo } from "react";
import { motion } from "framer-motion";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  TooltipProps,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FailureAggregate } from "@/lib/types";

interface FailureChartProps {
  failures: FailureAggregate[];
  threshold?: number;
}

interface ChartDatum {
  name: string;
  count: number;
  fullKey: string;
}

function CustomTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;
  const value = payload[0]?.value ?? 0;
  return (
    <div className="rounded-lg border bg-background px-3 py-2 shadow-md text-sm">
      <p className="font-semibold text-foreground truncate max-w-[200px]">{label}</p>
      <p className="text-muted-foreground">
        Occurrences:{" "}
        <span className="font-medium text-foreground">{value}</span>
      </p>
    </div>
  );
}

export function FailureChart({ failures, threshold = 2 }: FailureChartProps) {
  const data: ChartDatum[] = useMemo(() => {
    return [...failures]
      .sort((a, b) => b.occurrence_count - a.occurrence_count)
      .map((f) => ({
        name:
          f.failure_key.length > 22
            ? f.failure_key.slice(0, 22) + "…"
            : f.failure_key,
        count: f.occurrence_count,
        fullKey: f.failure_key,
      }));
  }, [failures]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: "easeOut" }}
    >
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">
            Failure Distribution
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Occurrence counts per failure key — dashed line marks the breach
            threshold
          </p>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart
              data={data}
              margin={{ top: 10, right: 20, left: 0, bottom: 60 }}
            >
              <defs>
                <linearGradient id="fillBelow" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="fillAbove" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid
                strokeDasharray="3 3"
                className="stroke-border"
                vertical={false}
              />
              <XAxis
                dataKey="name"
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                angle={-35}
                textAnchor="end"
                interval={0}
                height={64}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                allowDecimals={false}
                width={32}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine
                y={threshold}
                stroke="#f97316"
                strokeDasharray="6 3"
                strokeWidth={2}
                label={{
                  value: "Threshold",
                  position: "insideTopRight",
                  fontSize: 11,
                  fill: "#f97316",
                  fontWeight: 600,
                }}
              />
              {/* Blue area for values below threshold */}
              <Area
                type="monotone"
                dataKey="count"
                stroke="#3b82f6"
                strokeWidth={2}
                fill="url(#fillBelow)"
                dot={{ r: 4, fill: "#3b82f6", strokeWidth: 0 }}
                activeDot={{ r: 6 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </motion.div>
  );
}
