"use client";

import React, { useMemo } from "react";
import { motion } from "framer-motion";
import { Loader2, Stethoscope } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/shared/status-badge";
import { ThresholdIndicator } from "@/components/failures/threshold-indicator";
import { cn } from "@/lib/utils";
import { FailureAggregate } from "@/lib/types";

interface FailureTableProps {
  failures: FailureAggregate[];
  threshold: number;
  onDiagnose: (failureKey: string) => void;
  diagnosingKey?: string | null;
}

function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

const rowVariants = {
  hidden: { opacity: 0, x: -12 },
  visible: (i: number) => ({
    opacity: 1,
    x: 0,
    transition: { duration: 0.3, ease: "easeOut", delay: i * 0.05 },
  }),
};

export function FailureTable({
  failures,
  threshold,
  onDiagnose,
  diagnosingKey = null,
}: FailureTableProps) {
  const sorted = useMemo(
    () => [...failures].sort((a, b) => b.occurrence_count - a.occurrence_count),
    [failures]
  );

  function getStatusVariant(count: number, thres: number) {
    if (count >= thres) return "error" as const;
    if (count >= thres * 0.75) return "warning" as const;
    return "success" as const;
  }

  function getStatusLabel(count: number, thres: number) {
    if (count >= thres) return "Breached";
    if (count >= thres * 0.75) return "Approaching";
    return "Healthy";
  }

  return (
    <div className="rounded-lg border overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40">
            <TableHead className="w-[260px]">Failure Summary</TableHead>
            <TableHead>Evaluator</TableHead>
            <TableHead className="w-[160px]">Count vs Threshold</TableHead>
            <TableHead>First Seen</TableHead>
            <TableHead>Last Seen</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Action</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((failure, index) => {
            const isAbove = failure.occurrence_count >= threshold;
            const isApproaching =
              !isAbove &&
              failure.occurrence_count >= Math.ceil(threshold * 0.75);

            return (
              <motion.tr
                key={failure.failure_key}
                custom={index}
                initial="hidden"
                animate="visible"
                variants={rowVariants}
                className={cn(
                  "border-b transition-colors",
                  isAbove
                    ? "bg-red-50/60 dark:bg-red-950/30 hover:bg-red-100/60 dark:hover:bg-red-900/30"
                    : isApproaching
                    ? "bg-amber-50/60 dark:bg-amber-950/30 hover:bg-amber-100/60 dark:hover:bg-amber-900/30"
                    : "hover:bg-muted/30"
                )}
              >
                <TableCell className="font-medium text-sm py-3 max-w-[260px]">
                  <span
                    className="block truncate"
                    title={failure.failure_summary}
                  >
                    {failure.failure_summary || failure.failure_key}
                  </span>
                  <span className="block text-xs text-muted-foreground truncate mt-0.5">
                    {failure.failure_key}
                  </span>
                </TableCell>

                <TableCell className="text-sm py-3">
                  <span className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded">
                    {failure.evaluator_name}
                  </span>
                </TableCell>

                <TableCell className="py-3 min-w-[160px]">
                  <ThresholdIndicator
                    current={failure.occurrence_count}
                    threshold={threshold}
                    label=""
                  />
                  <span className="text-xs text-muted-foreground mt-1 block">
                    {failure.occurrence_count} of {threshold}
                  </span>
                </TableCell>

                <TableCell className="text-sm py-3 text-muted-foreground whitespace-nowrap">
                  {formatRelativeTime(failure.first_seen_at)}
                </TableCell>

                <TableCell className="text-sm py-3 text-muted-foreground whitespace-nowrap">
                  {formatRelativeTime(failure.last_seen_at)}
                </TableCell>

                <TableCell className="py-3">
                  <StatusBadge
                    status={getStatusVariant(failure.occurrence_count, threshold)}
                    label={getStatusLabel(failure.occurrence_count, threshold)}
                    pulse={isAbove}
                  />
                </TableCell>

                <TableCell className="py-3 text-right">
                  <Button
                    size="sm"
                    variant={isAbove ? "default" : "outline"}
                    onClick={() => onDiagnose(failure.failure_key)}
                    disabled={diagnosingKey === failure.failure_key}
                    className="gap-1.5"
                  >
                    {diagnosingKey === failure.failure_key ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Stethoscope className="h-3.5 w-3.5" />
                    )}
                    {diagnosingKey === failure.failure_key
                      ? "Creating…"
                      : "Diagnose"}
                  </Button>
                </TableCell>
              </motion.tr>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
