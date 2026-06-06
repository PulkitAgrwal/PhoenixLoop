"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  ArrowRight,
  CheckSquare,
  Gauge,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { StatCard } from "@/components/shared/stat-card";
import { TableSkeleton } from "@/components/shared/loading-skeleton";
import { StatusBadge } from "@/components/shared/status-badge";
import { ScoreGauge } from "@/components/release-gate/score-gauge";
import { GateChecklist } from "@/components/release-gate/gate-checklist";
import { ApprovalCard } from "@/components/release-gate/approval-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { ReleaseDecision, ReleaseGateDecision } from "@/lib/types";
import { cn } from "@/lib/utils";

// ─── Helpers ─────────────────────────────────────────────────────────────────

type StatusVariant = "success" | "error" | "warning" | "info" | "pending";

function decisionVariant(decision: ReleaseDecision): StatusVariant {
  switch (decision) {
    case "promoted":
      return "success";
    case "rejected":
      return "error";
    case "pending_human_review":
      return "warning";
    case "blocked_critical_failure":
      return "error";
  }
}

function decisionLabel(decision: ReleaseDecision): string {
  switch (decision) {
    case "promoted":
      return "Promoted";
    case "rejected":
      return "Rejected";
    case "pending_human_review":
      return "Pending Review";
    case "blocked_critical_failure":
      return "Blocked";
  }
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.slice(0, 8) + "…";
}

// ─── Decision Detail Panel ────────────────────────────────────────────────────

interface DecisionDetailProps {
  decision: ReleaseGateDecision;
  onRefresh: () => void;
}

function DecisionDetail({ decision, onRefresh }: DecisionDetailProps) {
  const totalRules = 6;
  const passed = decision.promotion_rules_passed;
  const score = decision.release_score;

  return (
    <motion.div
      key={decision.release_gate_decision_id}
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -16 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="space-y-5"
    >
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-0.5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Decision Detail
          </h2>
          <p className="font-mono text-sm text-foreground">
            {shortId(decision.release_gate_decision_id)}
          </p>
          <p className="text-xs text-muted-foreground">
            Experiment: {shortId(decision.experiment_id)}
          </p>
        </div>
        <StatusBadge
          status={decisionVariant(decision.decision)}
          label={decisionLabel(decision.decision)}
          pulse={decision.decision === "pending_human_review"}
        />
      </div>

      <Separator />

      {/* Score gauge + summary stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-[auto_1fr]">
        <div className="flex justify-center">
          <ScoreGauge score={score} label="Release Score" />
        </div>

        <div className="grid grid-cols-2 gap-3 self-center">
          <StatCard
            title="Rules Passed"
            value={`${passed} / ${totalRules}`}
            description="Promotion criteria"
            icon={<CheckSquare className="h-4 w-4" />}
          />
          <StatCard
            title="Release Score"
            value={(score * 100).toFixed(1)}
            description="Composite quality score"
            icon={<Gauge className="h-4 w-4" />}
          />
        </div>
      </div>

      <Separator />

      {/* Gate Checklist */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Promotion Criteria
        </h3>
        <GateChecklist rulesDetail={decision.rules_detail_json} />
      </div>

      <Separator />

      {/* Approval Card */}
      <ApprovalCard
        decisionId={decision.release_gate_decision_id}
        decision={decision.decision}
        decidedAt={decision.decided_at}
        onApprove={onRefresh}
        onReject={onRefresh}
      />
    </motion.div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ReleaseGatePage() {
  const router = useRouter();

  const [decisions, setDecisions] = useState<ReleaseGateDecision[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDecision, setSelectedDecision] =
    useState<ReleaseGateDecision | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  // ── Load list ──
  const loadList = useCallback(async () => {
    setListError(null);
    setLoadingList(true);
    try {
      const res = await api.releaseGate.list();
      if (res.ok && res.data) {
        const raw = res.data as
          | ReleaseGateDecision[]
          | { items: ReleaseGateDecision[] };
        setDecisions(
          Array.isArray(raw)
            ? raw
            : (raw as { items: ReleaseGateDecision[] }).items ?? []
        );
      } else {
        setListError(res.error ?? "Failed to load release gate decisions");
      }
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Unexpected error");
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  // ── Load detail ──
  const loadDetail = useCallback(
    async (id: string) => {
      setLoadingDetail(true);
      try {
        const res = await api.releaseGate.get(id);
        if (res.ok && res.data) {
          // GET /api/release-gate/{id} wraps the decision as
          // { decision, experiment, human_approval } — unwrap before storing.
          const raw = res.data as
            | ReleaseGateDecision
            | { decision: ReleaseGateDecision };
          const decision =
            "decision" in raw &&
            raw.decision &&
            typeof raw.decision === "object"
              ? (raw.decision as ReleaseGateDecision)
              : (raw as ReleaseGateDecision);
          setSelectedDecision(decision);
        }
      } catch {
        // Fall back to list item
        const found = decisions.find((d) => d.release_gate_decision_id === id);
        if (found) setSelectedDecision(found);
      } finally {
        setLoadingDetail(false);
      }
    },
    [decisions]
  );

  const handleSelectDecision = (id: string) => {
    setSelectedId(id);
    void loadDetail(id);
  };

  const handleRefresh = () => {
    void loadList();
    if (selectedId) void loadDetail(selectedId);
  };

  // ── Derived stats ──
  const totalDecisions = decisions.length;
  const pendingReview = decisions.filter(
    (d) => d.decision === "pending_human_review"
  ).length;
  const promoted = decisions.filter((d) => d.decision === "promoted").length;

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

      {/* Summary Stats */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
        className="grid grid-cols-1 gap-4 sm:grid-cols-3"
      >
        <StatCard
          title="Total Decisions"
          value={loadingList ? "—" : totalDecisions}
          description="All release gate evaluations"
          icon={<ShieldCheck className="h-4 w-4" />}
        />
        <StatCard
          title="Pending Review"
          value={loadingList ? "—" : pendingReview}
          description="Awaiting human approval"
          icon={<RefreshCw className="h-4 w-4" />}
        />
        <StatCard
          title="Promoted"
          value={loadingList ? "—" : promoted}
          description="Successfully promoted to production"
          icon={<CheckSquare className="h-4 w-4" />}
        />
      </motion.section>

      {/* Main split-pane layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[400px_1fr]">
        {/* ── Left: Decisions list ── */}
        <div className="flex flex-col gap-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Decisions
          </h2>

          {loadingList ? (
            <TableSkeleton rows={4} />
          ) : listError ? (
            <div className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-400">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {listError}
            </div>
          ) : decisions.length === 0 ? (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-lg border border-dashed border-border p-8 text-center space-y-3"
            >
              <ShieldCheck className="mx-auto h-8 w-8 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">
                No release decisions yet.
              </p>
              <p className="text-xs text-muted-foreground">
                Run an experiment first to generate a release gate evaluation.
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => router.push("/healing/experiments")}
                className="gap-1.5"
              >
                Go to Experiments
                <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </motion.div>
          ) : (
            <div className="rounded-lg border border-border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/40">
                    <TableHead className="text-xs">Experiment</TableHead>
                    <TableHead className="text-xs">Status</TableHead>
                    <TableHead className="text-xs text-right">Score</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {decisions.map((d, idx) => (
                    <motion.tr
                      key={d.release_gate_decision_id}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.2, delay: idx * 0.04 }}
                      onClick={() =>
                        handleSelectDecision(d.release_gate_decision_id)
                      }
                      className={cn(
                        "cursor-pointer border-b border-border transition-colors",
                        "hover:bg-muted/50",
                        selectedId === d.release_gate_decision_id &&
                          "bg-primary/5 hover:bg-primary/5"
                      )}
                    >
                      <TableCell className="py-3">
                        <div className="space-y-1">
                          <p className="font-mono text-xs truncate max-w-[140px]">
                            {shortId(d.experiment_id)}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {formatDateTime(d.decided_at)}
                          </p>
                        </div>
                      </TableCell>
                      <TableCell className="py-3">
                        <div className="space-y-1">
                          <StatusBadge
                            status={decisionVariant(d.decision)}
                            label={decisionLabel(d.decision)}
                            pulse={d.decision === "pending_human_review"}
                          />
                          <p className="text-xs text-muted-foreground">
                            {d.promotion_rules_passed}/6 rules
                          </p>
                        </div>
                      </TableCell>
                      <TableCell className="py-3 text-right">
                        <Badge
                          variant="outline"
                          className={cn(
                            "font-mono text-xs",
                            d.release_score >= 0.8 &&
                              "border-green-300 bg-green-50 text-green-700 dark:border-green-700 dark:bg-green-950 dark:text-green-400",
                            d.release_score >= 0.5 &&
                              d.release_score < 0.8 &&
                              "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-400",
                            d.release_score < 0.5 &&
                              "border-red-300 bg-red-50 text-red-700 dark:border-red-700 dark:bg-red-950 dark:text-red-400"
                          )}
                        >
                          {(d.release_score * 100).toFixed(0)}
                        </Badge>
                      </TableCell>
                    </motion.tr>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>

        {/* ── Right: Detail panel ── */}
        <div>
          <AnimatePresence mode="wait">
            {!selectedId ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex h-full min-h-[360px] items-center justify-center rounded-lg border border-dashed border-border"
              >
                <div className="space-y-2 text-center">
                  <ShieldCheck className="mx-auto h-8 w-8 text-muted-foreground/40" />
                  <p className="text-sm font-medium text-muted-foreground">
                    Select a decision to view details
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
                    className="h-28 animate-pulse rounded-lg border border-border bg-muted/30"
                  />
                ))}
              </motion.div>
            ) : selectedDecision ? (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-muted-foreground" />
                    Gate Evaluation
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-0">
                  <DecisionDetail
                    decision={selectedDecision}
                    onRefresh={handleRefresh}
                  />
                </CardContent>
              </Card>
            ) : null}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
