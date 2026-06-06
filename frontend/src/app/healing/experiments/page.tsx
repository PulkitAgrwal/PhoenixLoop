"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  ArrowRight,
  FlaskConical,
  RefreshCw,
} from "lucide-react";
import { StatusBadge } from "@/components/shared/status-badge";
import { TableSkeleton } from "@/components/shared/loading-skeleton";
import { ScoreComparison } from "@/components/experiments/score-comparison";
import { EvalBarChart } from "@/components/experiments/eval-bar-chart";
import { RegressionResults } from "@/components/experiments/regression-results";
import { PromptChangesSection } from "@/components/experiments/prompt-changes-section";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import {
  ExperimentRecord,
  ExperimentStatus,
  ReleaseDecision,
  ReleaseGateDecision,
} from "@/lib/types";
import { cn } from "@/lib/utils";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function experimentStatusVariant(
  status: ExperimentStatus
): "warning" | "info" | "success" | "error" | "pending" {
  switch (status) {
    case "pending":
      return "warning";
    case "running":
      return "info";
    case "completed":
      return "success";
    case "failed":
      return "error";
  }
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function scoreDelta(
  baseline: number | null,
  candidate: number | null
): string {
  if (baseline == null || candidate == null) return "—";
  const delta = (candidate - baseline) * 100;
  return `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}`;
}

function scoreDeltaPositive(
  baseline: number | null,
  candidate: number | null
): boolean | null {
  if (baseline == null || candidate == null) return null;
  return candidate >= baseline;
}

// ─── Verdict Badge ────────────────────────────────────────────────────────────

interface VerdictBadgeProps {
  decision: ReleaseDecision;
}

const verdictConfig: Record<
  ReleaseDecision,
  { label: string; className: string }
> = {
  promoted: {
    label: "PROMOTED",
    className:
      "border-emerald-300 bg-emerald-100 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  },
  rejected: {
    label: "REJECTED",
    className:
      "border-red-300 bg-red-100 text-red-800 dark:border-red-700 dark:bg-red-950 dark:text-red-300",
  },
  pending_human_review: {
    label: "PENDING REVIEW",
    className:
      "border-amber-300 bg-amber-100 text-amber-800 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-300",
  },
  blocked_critical_failure: {
    label: "BLOCKED",
    className:
      "border-red-300 bg-red-100 text-red-800 dark:border-red-700 dark:bg-red-950 dark:text-red-300",
  },
};

function VerdictBadge({ decision }: VerdictBadgeProps) {
  const config = verdictConfig[decision];
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3, type: "spring", stiffness: 300, damping: 20 }}
    >
      <Badge
        variant="outline"
        className={cn(
          "px-3 py-1 text-sm font-bold tracking-wide",
          config.className
        )}
      >
        {config.label}
      </Badge>
    </motion.div>
  );
}

// ─── Experiment Detail Panel ───────────────────────────────────────────────────

interface ExperimentDetailProps {
  experiment: ExperimentRecord;
  releaseGate: ReleaseGateDecision | null;
  baselinePromptText: string | null;
  candidatePromptText: string | null;
}

function ExperimentDetail({
  experiment,
  releaseGate,
  baselinePromptText,
  candidatePromptText,
}: ExperimentDetailProps) {
  const router = useRouter();

  return (
    <div className="space-y-5">
      {/* Verdict */}
      {releaseGate && (
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="space-y-0.5">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Release Decision
            </p>
            <p className="text-xs text-muted-foreground">
              Score:{" "}
              <span className="font-mono tabular-nums">
                {(releaseGate.release_score * 100).toFixed(1)}
              </span>{" "}
              · Rules passed:{" "}
              <span className="font-mono tabular-nums">
                {releaseGate.promotion_rules_passed}
              </span>
            </p>
          </div>
          <VerdictBadge decision={releaseGate.decision} />
        </div>
      )}

      {/* Score Comparison */}
      <ScoreComparison experiment={experiment} />

      {/* Prompt Changes (collapsible diff between baseline and candidate) */}
      <PromptChangesSection
        baseline={baselinePromptText}
        candidate={candidatePromptText}
        baselineVersion={experiment.baseline_prompt_version}
        candidateVersion={experiment.candidate_prompt_version}
      />

      <Separator />

      {/* Bar Chart */}
      <EvalBarChart experiment={experiment} />

      <Separator />

      {/* Regression Results */}
      <RegressionResults
        passRate={experiment.regression_cases_pass_rate}
        safetyRate={experiment.safety_canary_pass_rate}
      />

      {/* Action buttons */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <Button
          size="sm"
          variant="outline"
          className="gap-2"
          onClick={() => router.push("/healing/release-gate")}
        >
          View Release Gate
          <ArrowRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

interface ExperimentDetailData {
  experiment: ExperimentRecord;
  release_gate_decision: ReleaseGateDecision | null;
  baseline_prompt_text: string | null;
  candidate_prompt_text: string | null;
}

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<ExperimentRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] =
    useState<ExperimentDetailData | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  // Load experiments list
  const loadList = useCallback(async () => {
    setListError(null);
    setLoadingList(true);
    try {
      const res = await api.experiments.list();
      if (res.ok && res.data) {
        const raw = res.data as
          | ExperimentRecord[]
          | { items: ExperimentRecord[] };
        setExperiments(
          Array.isArray(raw)
            ? raw
            : (raw as { items: ExperimentRecord[] }).items ?? []
        );
      } else {
        setListError(res.error ?? "Failed to load experiments");
      }
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Unexpected error");
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  // Load detail when selectedId changes
  const loadDetail = useCallback(async (id: string) => {
    setLoadingDetail(true);
    try {
      const res = await api.experiments.get(id);
      if (res.ok && res.data) {
        const raw = res.data as ExperimentDetailData;
        setSelectedDetail(raw);
      }
    } catch {
      // silently ignore
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  const handleSelectExperiment = (id: string) => {
    setSelectedId(id);
    setSelectedDetail(null);
    loadDetail(id);
  };

  const handleRefresh = () => {
    loadList();
    if (selectedId) loadDetail(selectedId);
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          className="gap-2"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[400px_1fr]">
        {/* ── Left: Experiments List ── */}
        <div className="flex flex-col gap-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Experiments
          </h2>

          {loadingList ? (
            <TableSkeleton rows={4} />
          ) : listError ? (
            <div className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-400">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {listError}
            </div>
          ) : experiments.length === 0 ? (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-lg border border-dashed border-border p-6 text-center"
            >
              <FlaskConical className="mx-auto mb-2 h-8 w-8 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">
                No experiments yet.
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Create one from the{" "}
                <Link
                  href="/healing/improvements"
                  className="text-primary underline-offset-4 hover:underline"
                >
                  Improvements
                </Link>{" "}
                page.
              </p>
            </motion.div>
          ) : (
            <div className="rounded-lg border border-border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/40">
                    <TableHead className="text-xs">ID / Versions</TableHead>
                    <TableHead className="text-xs">Status</TableHead>
                    <TableHead className="text-xs text-right">Delta</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {experiments.map((exp, idx) => {
                    const delta = scoreDelta(
                      exp.baseline_release_score,
                      exp.candidate_release_score
                    );
                    const deltaPos = scoreDeltaPositive(
                      exp.baseline_release_score,
                      exp.candidate_release_score
                    );

                    return (
                      <motion.tr
                        key={exp.experiment_id}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.2, delay: idx * 0.04 }}
                        onClick={() =>
                          handleSelectExperiment(exp.experiment_id)
                        }
                        className={cn(
                          "cursor-pointer border-b border-border transition-colors",
                          "hover:bg-muted/50",
                          selectedId === exp.experiment_id &&
                            "bg-primary/5 hover:bg-primary/5"
                        )}
                      >
                        <TableCell className="py-3">
                          <div className="space-y-1">
                            <p className="text-xs font-mono truncate max-w-[160px] text-muted-foreground">
                              {exp.experiment_id.slice(0, 16)}…
                            </p>
                            <div className="flex flex-wrap gap-1">
                              <Badge
                                variant="secondary"
                                className="text-[10px] px-1.5 py-0"
                              >
                                {exp.baseline_prompt_version}
                              </Badge>
                              <span className="text-[10px] text-muted-foreground self-center">
                                →
                              </span>
                              <Badge
                                variant="secondary"
                                className="text-[10px] px-1.5 py-0"
                              >
                                {exp.candidate_prompt_version}
                              </Badge>
                            </div>
                            <p className="text-[10px] text-muted-foreground/60">
                              {formatDate(exp.created_at)}
                            </p>
                          </div>
                        </TableCell>
                        <TableCell className="py-3">
                          <StatusBadge
                            status={experimentStatusVariant(exp.status)}
                            label={exp.status}
                            pulse={exp.status === "running"}
                          />
                        </TableCell>
                        <TableCell className="py-3 text-right">
                          <span
                            className={cn(
                              "text-xs font-mono tabular-nums font-medium",
                              deltaPos === null
                                ? "text-muted-foreground"
                                : deltaPos
                                ? "text-emerald-600 dark:text-emerald-400"
                                : "text-red-500 dark:text-red-400"
                            )}
                          >
                            {delta}
                          </span>
                        </TableCell>
                      </motion.tr>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </div>

        {/* ── Right: Detail Panel ── */}
        <div>
          <AnimatePresence mode="wait">
            {!selectedId ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex h-full min-h-[320px] items-center justify-center rounded-lg border border-dashed border-border"
              >
                <div className="text-center space-y-2">
                  <FlaskConical className="mx-auto h-8 w-8 text-muted-foreground/40" />
                  <p className="text-sm font-medium text-muted-foreground">
                    Select an experiment to view results
                  </p>
                </div>
              </motion.div>
            ) : loadingDetail ? (
              <motion.div
                key="loading"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="space-y-4"
              >
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-32 rounded-lg border border-border bg-muted/30 animate-pulse"
                  />
                ))}
              </motion.div>
            ) : selectedDetail ? (
              <motion.div
                key={selectedDetail.experiment.experiment_id}
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -16 }}
                transition={{ duration: 0.25, ease: "easeOut" }}
              >
                {/* Detail header */}
                <div className="mb-4 flex items-start justify-between gap-3 flex-wrap">
                  <div className="space-y-1">
                    <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Detail
                    </h2>
                    <p className="text-xs font-mono text-muted-foreground">
                      {selectedDetail.experiment.experiment_id}
                    </p>
                  </div>
                  <StatusBadge
                    status={experimentStatusVariant(
                      selectedDetail.experiment.status
                    )}
                    label={selectedDetail.experiment.status}
                    pulse={selectedDetail.experiment.status === "running"}
                  />
                </div>

                <ExperimentDetail
                  experiment={selectedDetail.experiment}
                  releaseGate={selectedDetail.release_gate_decision}
                  baselinePromptText={selectedDetail.baseline_prompt_text}
                  candidatePromptText={selectedDetail.candidate_prompt_text}
                />
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
