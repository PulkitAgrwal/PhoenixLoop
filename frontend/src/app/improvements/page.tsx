"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  ArrowRight,
  Brain,
  FlaskConical,
  Loader2,
  RefreshCw,
  Zap,
} from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { StatusBadge } from "@/components/shared/status-badge";
import { TableSkeleton } from "@/components/shared/loading-skeleton";
import { EvidenceCard } from "@/components/improvements/evidence-card";
import { McpQueryLog } from "@/components/improvements/mcp-query-log";
import { PromptDiff } from "@/components/improvements/prompt-diff";
import { RegressionList } from "@/components/improvements/regression-list";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { ImprovementTrigger, TriggerReason } from "@/lib/types";
import { cn } from "@/lib/utils";

// ─── helpers ────────────────────────────────────────────────────────────────

type TriggerStatus =
  | "pending"
  | "diagnosed"
  | "regressions_generated"
  | "experiment_complete"
  | "closed";

function statusVariant(
  status: string
): "warning" | "info" | "success" | "pending" {
  switch (status as TriggerStatus) {
    case "diagnosed":
      return "info";
    case "regressions_generated":
      return "info";
    case "experiment_complete":
      return "success";
    case "closed":
      return "pending";
    default:
      return "warning";
  }
}

function triggerReasonLabel(reason: TriggerReason): string {
  switch (reason) {
    case "threshold_repeated_failure":
      return "Repeated Failure";
    case "critical_failure":
      return "Critical";
    case "manual_demo_trigger":
      return "Manual";
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

// ─── Root Cause Card ─────────────────────────────────────────────────────────

function RootCauseCard({
  diagnosis,
}: {
  diagnosis: Record<string, unknown> | null;
}) {
  if (!diagnosis) return null;

  const confidence = diagnosis["confidence"];
  const confidenceDisplay =
    typeof confidence === "number"
      ? `${(confidence * 100).toFixed(0)}%`
      : typeof confidence === "string"
      ? confidence
      : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
    >
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-muted-foreground" />
              <CardTitle className="text-sm font-semibold">
                Root Cause Analysis
              </CardTitle>
            </div>
            {confidenceDisplay && (
              <Badge
                variant="outline"
                className="text-xs border-purple-300 bg-purple-50 text-purple-700 dark:border-purple-800 dark:bg-purple-950 dark:text-purple-400"
              >
                {confidenceDisplay} confidence
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="pt-0 space-y-3">
          {diagnosis["failure_pattern"] != null && (
            <Field
              label="Failure Pattern"
              value={String(diagnosis["failure_pattern"])}
            />
          )}
          {diagnosis["root_cause"] != null && (
            <Field
              label="Root Cause"
              value={String(diagnosis["root_cause"])}
              highlight
            />
          )}
          {diagnosis["evidence_summary"] != null && (
            <Field
              label="Evidence Summary"
              value={String(diagnosis["evidence_summary"])}
            />
          )}
          {diagnosis["proposed_fix"] != null && (
            <Field
              label="Proposed Fix"
              value={String(diagnosis["proposed_fix"])}
            />
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

function Field({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="space-y-0.5">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p
        className={cn(
          "text-sm leading-relaxed",
          highlight ? "font-medium text-foreground" : "text-muted-foreground"
        )}
      >
        {value}
      </p>
    </div>
  );
}

// ─── Trigger Detail Panel ────────────────────────────────────────────────────

interface TriggerDetailProps {
  trigger: ImprovementTrigger;
  onRefresh: () => void;
}

function TriggerDetail({ trigger, onRefresh }: TriggerDetailProps) {
  const router = useRouter();
  const [analyzingId, setAnalyzingId] = useState<string | null>(null);
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const canAnalyze = trigger.diagnosis_json == null;
  const canGenerateRegressions =
    trigger.regression_examples_json == null ||
    trigger.regression_examples_json.length === 0;
  const canRunExperiment =
    trigger.status !== "experiment_complete" && trigger.status !== "closed";

  const handleAnalyze = async () => {
    setActionError(null);
    setAnalyzingId(trigger.improvement_trigger_id);
    try {
      const res = await api.improvements.analyze(
        trigger.improvement_trigger_id
      );
      if (!res.ok) {
        setActionError(res.error ?? "Analysis failed");
      } else {
        onRefresh();
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Unexpected error");
    } finally {
      setAnalyzingId(null);
    }
  };

  const handleGenerateRegressions = async () => {
    setActionError(null);
    setGeneratingId(trigger.improvement_trigger_id);
    try {
      const res = await api.improvements.generateRegressions(
        trigger.improvement_trigger_id
      );
      if (!res.ok) {
        setActionError(res.error ?? "Generation failed");
      } else {
        onRefresh();
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Unexpected error");
    } finally {
      setGeneratingId(null);
    }
  };

  const handleRunExperiment = async () => {
    setActionError(null);
    setRunningId(trigger.improvement_trigger_id);
    try {
      const res = await api.experiments.run(trigger.improvement_trigger_id);
      if (!res.ok) {
        setActionError(res.error ?? "Experiment run failed");
      } else {
        router.push("/experiments");
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Unexpected error");
    } finally {
      setRunningId(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Action bar */}
      <div className="flex flex-wrap items-center gap-2">
        {canAnalyze && (
          <Button
            size="sm"
            className="gap-2"
            onClick={handleAnalyze}
            disabled={analyzingId != null}
          >
            {analyzingId != null ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Brain className="h-3.5 w-3.5" />
            )}
            {analyzingId != null ? "Analyzing…" : "Analyze"}
          </Button>
        )}
        {canGenerateRegressions && (
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={handleGenerateRegressions}
            disabled={generatingId != null}
          >
            {generatingId != null ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Zap className="h-3.5 w-3.5" />
            )}
            {generatingId != null
              ? "Generating…"
              : "Generate Regressions"}
          </Button>
        )}
        {canRunExperiment && (
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={handleRunExperiment}
            disabled={runningId != null}
          >
            {runningId != null ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <FlaskConical className="h-3.5 w-3.5" />
            )}
            {runningId != null ? "Starting…" : "Run Experiment"}
            {runningId == null && (
              <ArrowRight className="h-3 w-3 ml-0.5" />
            )}
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          className="gap-2 ml-auto"
          onClick={onRefresh}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>

      {/* Error alert */}
      <AnimatePresence>
        {actionError && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-400"
          >
            <AlertCircle className="h-4 w-4 shrink-0" />
            {actionError}
          </motion.div>
        )}
      </AnimatePresence>

      <Separator />

      {/* Evidence */}
      <EvidenceCard
        exampleRunIds={trigger.example_run_ids_json ?? []}
        failureKey={trigger.failure_key}
      />

      {/* MCP Query Log (diagnosis process) */}
      <McpQueryLog diagnosis={trigger.diagnosis_json} />

      {/* Root cause */}
      {trigger.diagnosis_json && (
        <RootCauseCard diagnosis={trigger.diagnosis_json} />
      )}

      {/* Prompt diff */}
      <PromptDiff proposal={trigger.patch_proposal_json} />

      {/* Regression tests */}
      <RegressionList
        regressions={trigger.regression_examples_json ?? []}
      />
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function ImprovementsPage() {
  const [triggers, setTriggers] = useState<ImprovementTrigger[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedTrigger, setSelectedTrigger] =
    useState<ImprovementTrigger | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  // Load list
  const loadList = useCallback(async () => {
    setListError(null);
    setLoadingList(true);
    try {
      const res = await api.improvements.list();
      if (res.ok && res.data) {
        const raw = res.data as ImprovementTrigger[] | { items: ImprovementTrigger[] };
        setTriggers(Array.isArray(raw) ? raw : (raw as { items: ImprovementTrigger[] }).items ?? []);
      } else {
        setListError(res.error ?? "Failed to load improvement triggers");
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
  const loadDetail = useCallback(
    async (id: string) => {
      setLoadingDetail(true);
      try {
        const res = await api.improvements.get(id);
        if (res.ok && res.data) {
          setSelectedTrigger(res.data as ImprovementTrigger);
        }
      } catch {
        // Silently fall back to list data
        const found = triggers.find((t) => t.improvement_trigger_id === id);
        if (found) setSelectedTrigger(found);
      } finally {
        setLoadingDetail(false);
      }
    },
    [triggers]
  );

  const handleSelectTrigger = (id: string) => {
    setSelectedId(id);
    loadDetail(id);
  };

  const handleRefresh = () => {
    loadList();
    if (selectedId) loadDetail(selectedId);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Improvement Proposals"
        description="Root cause analysis and prompt repair suggestions"
        actions={
          <Button variant="outline" size="sm" onClick={handleRefresh} className="gap-2">
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr]">
        {/* ── Left: Triggers List ── */}
        <div className="flex flex-col gap-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Triggers
          </h2>

          {loadingList ? (
            <TableSkeleton rows={4} />
          ) : listError ? (
            <div className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-400">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {listError}
            </div>
          ) : triggers.length === 0 ? (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-lg border border-dashed border-border p-6 text-center"
            >
              <p className="text-sm text-muted-foreground">
                No improvement triggers yet.
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Failures crossing threshold will appear here.{" "}
                <a
                  href="/failures"
                  className="text-primary underline-offset-4 hover:underline"
                >
                  View failures
                </a>
              </p>
            </motion.div>
          ) : (
            <div className="rounded-lg border border-border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/40">
                    <TableHead className="text-xs">Failure Key</TableHead>
                    <TableHead className="text-xs">Reason</TableHead>
                    <TableHead className="text-xs text-right">#</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {triggers.map((t, idx) => (
                    <motion.tr
                      key={t.improvement_trigger_id}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.2, delay: idx * 0.04 }}
                      onClick={() =>
                        handleSelectTrigger(t.improvement_trigger_id)
                      }
                      className={cn(
                        "cursor-pointer border-b border-border transition-colors",
                        "hover:bg-muted/50",
                        selectedId === t.improvement_trigger_id &&
                          "bg-primary/5 hover:bg-primary/5"
                      )}
                    >
                      <TableCell className="py-3">
                        <div className="space-y-1">
                          <p className="text-xs font-mono truncate max-w-[160px]">
                            {t.failure_key}
                          </p>
                          <StatusBadge
                            status={statusVariant(t.status)}
                            label={t.status.replace(/_/g, " ")}
                          />
                        </div>
                      </TableCell>
                      <TableCell className="py-3">
                        <span className="text-xs text-muted-foreground">
                          {triggerReasonLabel(t.trigger_reason)}
                        </span>
                        <p className="text-xs text-muted-foreground/60 mt-0.5">
                          {formatDate(t.created_at)}
                        </p>
                      </TableCell>
                      <TableCell className="py-3 text-right">
                        <Badge variant="secondary" className="text-xs">
                          {t.occurrence_count}
                        </Badge>
                      </TableCell>
                    </motion.tr>
                  ))}
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
                  <Brain className="mx-auto h-8 w-8 text-muted-foreground/40" />
                  <p className="text-sm font-medium text-muted-foreground">
                    Select a trigger to view details
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
                  <div key={i} className="h-32 rounded-lg border border-border bg-muted/30 animate-pulse" />
                ))}
              </motion.div>
            ) : selectedTrigger ? (
              <motion.div
                key={selectedTrigger.improvement_trigger_id}
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -16 }}
                transition={{ duration: 0.25, ease: "easeOut" }}
              >
                {/* Detail header */}
                <div className="mb-4 flex items-center justify-between gap-3 flex-wrap">
                  <div className="space-y-1">
                    <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Detail
                    </h2>
                    <p className="text-sm font-mono text-foreground">
                      {selectedTrigger.failure_key}
                    </p>
                  </div>
                  <StatusBadge
                    status={statusVariant(selectedTrigger.status)}
                    label={selectedTrigger.status.replace(/_/g, " ")}
                  />
                </div>

                <TriggerDetail
                  trigger={selectedTrigger}
                  onRefresh={handleRefresh}
                />
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
