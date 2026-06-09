"use client";

import React, { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  CheckSquare,
  Gauge,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { StatCard } from "@/components/shared/stat-card";
import { TableSkeleton } from "@/components/shared/loading-skeleton";
import { StatusBadge } from "@/components/shared/status-badge";
import { PhoenixDeepLink } from "@/components/shared/phoenix-deep-link";
import { EmptyState } from "@/components/shared/empty-state";
import { ScoreGauge } from "@/components/release-gate/score-gauge";
import { ApprovalCard } from "@/components/release-gate/approval-card";
import { RuleRow, type RuleStatus } from "@/components/release-gate/rule-row";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Eyebrow } from "@/components/ui/eyebrow";
import { CodeInline } from "@/components/ui/code-inline";
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

// ─── 9-rule taxonomy ─────────────────────────────────────────────────────────

interface NormalizedRule {
  name: string;
  status: RuleStatus;
  required: string;
  actual: string;
}

// Original 6 quality rules. Order is significant — this is the legacy display
// order from the deprecated GateChecklist.
const QUALITY_RULE_NAMES = [
  "score_delta",
  "critical_failure",
  "hallucination",
  "latency",
  "regression",
  "safety_canary",
] as const;

// New (Wave 2b) multi-dimensional efficiency rules.
const EFFICIENCY_RULE_NAMES = [
  "tool_call_efficiency",
  "latency_tier",
  "tool_adherence",
] as const;

function coerceStatus(raw: unknown): RuleStatus {
  if (raw === "pass" || raw === true) return "pass";
  if (raw === "fail" || raw === false) return "fail";
  if (raw === "skipped" || raw === null || raw === undefined)
    return "skipped";
  return "skipped";
}

function stringifyMetric(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    if (Number.isInteger(value)) return value.toString();
    return value.toFixed(3);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

/**
 * Wave 2b ships rules_detail_json as an ordered array of
 * `{name, status, required, actual}`. The pre-2b shape was a
 * `Record<string, {passed, actual, threshold, baseline}>` map. Normalize
 * both shapes into the same `NormalizedRule` list, slotting unknown rule
 * names through but preserving the canonical ordering when possible.
 */
function normalizeRules(raw: unknown): NormalizedRule[] {
  if (Array.isArray(raw)) {
    return raw
      .map((entry) => {
        if (!entry || typeof entry !== "object") return null;
        const r = entry as Record<string, unknown>;
        const name = typeof r.name === "string" ? r.name : "";
        if (!name) return null;
        return {
          name,
          status: coerceStatus(r.status),
          required: stringifyMetric(r.required),
          actual: stringifyMetric(r.actual),
        } satisfies NormalizedRule;
      })
      .filter((x): x is NormalizedRule => x !== null);
  }
  if (raw && typeof raw === "object") {
    const map = raw as Record<string, unknown>;
    const order = [...QUALITY_RULE_NAMES, ...EFFICIENCY_RULE_NAMES];
    const out: NormalizedRule[] = [];
    for (const name of order) {
      const entry = map[name];
      if (!entry || typeof entry !== "object") continue;
      const r = entry as Record<string, unknown>;
      out.push({
        name,
        status: coerceStatus(r.passed ?? r.status),
        required: stringifyMetric(r.threshold ?? r.required),
        actual: stringifyMetric(r.actual),
      });
    }
    return out;
  }
  return [];
}

function partitionRules(rules: NormalizedRule[]): {
  quality: NormalizedRule[];
  efficiency: NormalizedRule[];
} {
  const qualitySet = new Set<string>(QUALITY_RULE_NAMES);
  const efficiencySet = new Set<string>(EFFICIENCY_RULE_NAMES);
  const quality: NormalizedRule[] = [];
  const efficiency: NormalizedRule[] = [];
  for (const r of rules) {
    if (efficiencySet.has(r.name)) efficiency.push(r);
    else if (qualitySet.has(r.name)) quality.push(r);
    else quality.push(r); // unknown rules tagged as quality by default
  }
  return { quality, efficiency };
}

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
  const rules = React.useMemo(
    () => normalizeRules(decision.rules_detail_json),
    [decision.rules_detail_json]
  );
  const { quality, efficiency } = React.useMemo(
    () => partitionRules(rules),
    [rules]
  );
  const evaluated = rules.filter((r) => r.status !== "skipped").length;
  const totalRules = rules.length || 9;
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
          <div className="pt-1">
            <PhoenixDeepLink
              experimentId={decision.experiment_id}
              label="View experiment in Phoenix"
            />
          </div>
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

      {/* Gate Rules — quality + new efficiency tier */}
      <div className="space-y-4">
        <div className="flex items-end justify-between gap-3">
          <Eyebrow tone="mute">Quality gates</Eyebrow>
          <span className="font-mono text-caption text-mute">
            {evaluated} evaluated · {totalRules} total
          </span>
        </div>
        <div className="space-y-2">
          {quality.length > 0 ? (
            quality.map((rule) => (
              <RuleRow
                key={`q-${rule.name}`}
                name={rule.name}
                status={rule.status}
                required={rule.required}
                actual={rule.actual}
              />
            ))
          ) : (
            <p className="text-body-sm text-mute">
              No quality rules reported on this decision yet.
            </p>
          )}
        </div>

        <div className="flex items-center gap-3 pt-2">
          <Eyebrow tone="brand">
            {"// new — multi-dim efficiency gates"}
          </Eyebrow>
          <span className="h-px flex-1 bg-hairline" aria-hidden />
        </div>
        <div className="space-y-2">
          {efficiency.length > 0 ? (
            efficiency.map((rule) => (
              <RuleRow
                key={`e-${rule.name}`}
                name={rule.name}
                status={rule.status}
                required={rule.required}
                actual={rule.actual}
              />
            ))
          ) : (
            <p className="text-body-sm text-mute">
              Efficiency rules not yet computed for this decision.
            </p>
          )}
        </div>
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
    <div className="mx-auto max-w-[1280px] px-5 py-10 lg:px-8 lg:py-14">
      <header className="flex flex-col gap-3">
        <Eyebrow tone="brand">Healing · Release gate</Eyebrow>
        <h1 className="text-display-lg text-ink-strong">
          One verdict per experiment. Nine rules each.
        </h1>
        <p className="max-w-[68ch] text-body-md text-body">
          The release gate scores each candidate prompt against six quality rules and three new
          multi-dimensional efficiency rules, then emits a single verdict —{" "}
          <CodeInline>PROMOTED</CodeInline>, <CodeInline>REJECTED</CodeInline>, or{" "}
          <CodeInline>PENDING REVIEW</CodeInline>. Critical failures block automatically.
        </p>
      </header>

      <div className="mt-8 space-y-6">
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
            <div className="flex items-center gap-2 rounded-md border border-fail/40 bg-fail/[0.06] px-3 py-2 text-body-sm text-fail">
              <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
              {listError}
            </div>
          ) : decisions.length === 0 ? (
            <EmptyState
              title="No release gate outcomes yet"
              description="Promotion decisions appear here after experiments complete. Run seed."
            />
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
                            {d.promotion_rules_passed} rules passed
                          </p>
                        </div>
                      </TableCell>
                      <TableCell className="py-3 text-right">
                        <Badge
                          variant="outline"
                          className={cn(
                            "font-mono text-xs",
                            d.release_score >= 0.8 &&
                              "border-brand/40 bg-brand/[0.08] text-brand-soft",
                            d.release_score >= 0.5 &&
                              d.release_score < 0.8 &&
                              "border-warn/40 bg-warn/[0.08] text-warn",
                            d.release_score < 0.5 &&
                              "border-fail/40 bg-fail/[0.08] text-fail"
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
    </div>
  );
}
