"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Activity,
  MessageSquare,
  ChevronDown,
  ChevronRight,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";

import { StatCard } from "@/components/shared/stat-card";
import { StatusBadge } from "@/components/shared/status-badge";
import { TableSkeleton } from "@/components/shared/loading-skeleton";
import { TraceWaterfall } from "@/components/traces/trace-waterfall";
import { SpanDetail } from "@/components/traces/span-detail";
import { EvalBadge } from "@/components/traces/eval-badge";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";

import { api } from "@/lib/api";
import {
  AgentRun,
  ConversationSession,
  EvalResult,
  ToolCallRecord,
  EvalType,
} from "@/lib/types";
import { cn } from "@/lib/utils";

// ─── Types ───────────────────────────────────────────────────────────────────

interface RunRow {
  run: AgentRun;
  session: ConversationSession;
  evals: EvalResult[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatLatency(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function getRunStatusVariant(
  status: string
): "success" | "error" | "warning" | "pending" {
  if (status === "completed" || status === "success") return "success";
  if (status === "failed" || status === "error") return "error";
  if (status === "running") return "warning";
  return "pending";
}

function countEvals(evals: EvalResult[]): { pass: number; fail: number } {
  let pass = 0;
  let fail = 0;
  for (const e of evals) {
    const isPass =
      e.outcome === "pass" || (e.score !== null && e.score >= 0.7);
    if (isPass) pass++;
    else fail++;
  }
  return { pass, fail };
}

// ─── Session Summary ──────────────────────────────────────────────────────────

function SessionSummary({
  run,
  evals,
}: {
  run: AgentRun;
  evals: EvalResult[];
}) {
  const { pass, fail } = countEvals(evals);
  const passRate = evals.length > 0 ? (pass / evals.length) * 100 : 0;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCard
        title="Total Evals"
        value={evals.length}
        icon={<Activity className="h-4 w-4" />}
        description="evaluators run"
      />
      <StatCard
        title="Passed"
        value={pass}
        icon={<CheckCircle2 className="h-4 w-4 text-green-500" />}
        description={`${passRate.toFixed(0)}% pass rate`}
      />
      <StatCard
        title="Failed"
        value={fail}
        icon={<XCircle className="h-4 w-4 text-red-500" />}
        description={fail > 0 ? "needs attention" : "all clear"}
      />
      <StatCard
        title="Latency"
        value={formatLatency(run.latency_ms)}
        icon={<Clock className="h-4 w-4" />}
        description={
          run.token_count_input
            ? `${run.token_count_input + (run.token_count_output ?? 0)} tokens`
            : undefined
        }
      />
    </div>
  );
}

// ─── Eval Results Grid ────────────────────────────────────────────────────────

const EVAL_TYPE_LABELS: Record<EvalType, string> = {
  code: "Code",
  llm_judge: "LLM Judge",
  phoenix_tool_eval: "Tool Eval",
};

function EvalGrid({ evals }: { evals: EvalResult[] }) {
  const byType: Record<EvalType, EvalResult[]> = {
    code: [],
    llm_judge: [],
    phoenix_tool_eval: [],
  };

  for (const e of evals) {
    if (e.eval_type in byType) {
      byType[e.eval_type as EvalType].push(e);
    }
  }

  const tabs: EvalType[] = ["code", "llm_judge", "phoenix_tool_eval"];
  const defaultTab: EvalType =
    tabs.find((t) => byType[t].length > 0) ?? "code";

  return (
    <Tabs defaultValue={defaultTab}>
      <TabsList className="mb-3">
        {tabs.map((type) => {
          const count = byType[type].length;
          return (
            <TabsTrigger key={type} value={type} disabled={count === 0}>
              {EVAL_TYPE_LABELS[type]}
              {count > 0 && (
                <Badge
                  variant="secondary"
                  className="ml-1.5 h-4 w-4 p-0 text-[10px] flex items-center justify-center"
                >
                  {count}
                </Badge>
              )}
            </TabsTrigger>
          );
        })}
      </TabsList>

      {tabs.map((type) => (
        <TabsContent key={type} value={type}>
          {byType[type].length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">
              No {EVAL_TYPE_LABELS[type]} evaluations for this run.
            </p>
          ) : (
            <motion.div
              className="flex flex-wrap gap-2"
              initial="hidden"
              animate="visible"
              variants={{
                hidden: {},
                visible: { transition: { staggerChildren: 0.04 } },
              }}
            >
              {byType[type].map((e) => (
                <motion.div
                  key={e.eval_result_id}
                  variants={{
                    hidden: { opacity: 0, scale: 0.8 },
                    visible: { opacity: 1, scale: 1 },
                  }}
                >
                  <EvalBadge evalResult={e} />
                </motion.div>
              ))}
            </motion.div>
          )}
        </TabsContent>
      ))}
    </Tabs>
  );
}

// ─── Run Detail Panel ─────────────────────────────────────────────────────────

function RunDetailPanel({
  runRow,
  onClose,
}: {
  runRow: RunRow;
  onClose: () => void;
}) {
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const toolCalls: ToolCallRecord[] = runRow.run.tool_calls_json ?? [];

  const handleSelectSpan = (
    _tc: ToolCallRecord | null,
    syntheticId: string | null,
  ) => {
    setSelectedSpanId(syntheticId);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 16 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="space-y-4"
    >
      {/* Summary cards */}
      <SessionSummary run={runRow.run} evals={runRow.evals} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Trace Waterfall with inline span detail (left 2/3) */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm font-semibold">
                    Trace Waterfall
                  </CardTitle>
                  <CardDescription className="text-xs mt-0.5">
                    {toolCalls.length} tool calls · total{" "}
                    {formatLatency(runRow.run.latency_ms)} · click a row to
                    inspect
                  </CardDescription>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs h-7"
                  onClick={onClose}
                >
                  Collapse
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <TraceWaterfall
                toolCalls={toolCalls}
                totalLatencyMs={runRow.run.latency_ms ?? 0}
                onSelectSpan={handleSelectSpan}
                selectedSpanId={selectedSpanId}
                renderSelectedDetail={(tc) => (
                  <SpanDetail toolCall={tc} evalResults={runRow.evals} />
                )}
              />
            </CardContent>
          </Card>
        </div>

        {/* Eval results grid (right 1/3) */}
        <div>
          <Card className="h-full">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">
                Eval Results
              </CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Grouped by evaluator type
              </CardDescription>
            </CardHeader>
            <CardContent>
              {runRow.evals.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No evaluations found for this run.
                </p>
              ) : (
                <EvalGrid evals={runRow.evals} />
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </motion.div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function TracesPage() {
  const [loading, setLoading] = useState(true);
  const [runRows, setRunRows] = useState<RunRow[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [loadingEvals, setLoadingEvals] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const searchParams = useSearchParams();
  const requestedRunId = searchParams?.get("run_id") ?? null;

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const sessionsRes = await api.conversations.list();
      if (!sessionsRes.ok || !sessionsRes.data) {
        setRunRows([]);
        setLoading(false);
        return;
      }

      // The /api/conversations response is paginated: items is ConversationSession[]
      const items = (
        sessionsRes.data as {
          items?: ConversationSession[];
        } & ConversationSession[]
      ) as unknown;

      let sessions: ConversationSession[] = [];
      if (Array.isArray(items)) {
        sessions = items as ConversationSession[];
      } else if (
        typeof items === "object" &&
        items !== null &&
        "items" in items
      ) {
        sessions = (items as { items: ConversationSession[] }).items;
      }

      // For each session, fetch runs and evals
      const rows: RunRow[] = [];
      for (const session of sessions.slice(0, 20)) {
        const detailRes = await api.conversations.get(
          session.conversation_session_id
        );
        if (!detailRes.ok || !detailRes.data) continue;

        // /api/conversations/{id} wraps each run as
        // { agent_run, eval_results, triggers_created } — unwrap and reuse
        // the embedded eval_results instead of refetching.
        const detail = detailRes.data as {
          session?: ConversationSession;
          runs?: Array<{
            agent_run: AgentRun;
            eval_results?: EvalResult[];
            triggers_created?: number;
          }>;
        };

        const runs = detail.runs ?? [];
        for (const wrapper of runs) {
          const run = wrapper.agent_run;
          const evalItems = wrapper.eval_results ?? [];
          rows.push({ run, session, evals: evalItems });
        }
      }

      // Sort newest first
      rows.sort(
        (a, b) =>
          new Date(b.run.created_at).getTime() -
          new Date(a.run.created_at).getTime()
      );
      setRunRows(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load traces");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // When the URL has ?run_id=… and the matching run is loaded, auto-expand it
  // and scroll it into view. Runs once per id; the user can collapse normally.
  useEffect(() => {
    if (!requestedRunId || runRows.length === 0) return;
    const exists = runRows.some(
      (r) => r.run.agent_run_id === requestedRunId,
    );
    if (exists && selectedRunId !== requestedRunId) {
      setSelectedRunId(requestedRunId);
      setTimeout(() => {
        const row = document.querySelector(
          `tr[data-run-id="${requestedRunId}"]`,
        );
        row?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 60);
    }
  }, [requestedRunId, runRows, selectedRunId]);

  // Load evals for newly selected run if not loaded
  const handleSelectRun = async (runId: string) => {
    if (selectedRunId === runId) {
      setSelectedRunId(null);
      return;
    }
    setSelectedRunId(runId);

    const existing = runRows.find((r) => r.run.agent_run_id === runId);
    if (existing && existing.evals.length > 0) return;

    // Fetch evals if not yet loaded
    setLoadingEvals(true);
    try {
      const evalsRes = await api.evals.getForRun(runId);
      if (evalsRes.ok && evalsRes.data) {
        const evalItems = Array.isArray(evalsRes.data)
          ? (evalsRes.data as EvalResult[])
          : ((evalsRes.data as { items?: EvalResult[] }).items ?? []);
        setRunRows((prev) =>
          prev.map((r) =>
            r.run.agent_run_id === runId ? { ...r, evals: evalItems } : r
          )
        );
      }
    } finally {
      setLoadingEvals(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button
          variant="outline"
          size="sm"
          onClick={loadData}
          disabled={loading}
        >
          <RefreshCw
            className={cn("h-4 w-4 mr-1.5", loading && "animate-spin")}
          />
          Refresh
        </Button>
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-950/30 px-4 py-3 text-sm text-red-700 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Agent Runs Table */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Agent Runs</CardTitle>
          <CardDescription className="text-xs">
            Click a row to inspect the trace and evaluation results
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="px-6 pb-4">
              <TableSkeleton rows={5} />
            </div>
          ) : runRows.length === 0 ? (
            /* Empty state */
            <div className="flex flex-col items-center justify-center gap-3 px-6 py-16">
              <MessageSquare className="h-10 w-10 text-muted-foreground/40" />
              <div className="text-center">
                <p className="text-sm font-medium text-muted-foreground">
                  No traces yet
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Run a conversation first to see traces here.
                </p>
              </div>
              <Button variant="outline" size="sm" asChild>
                <Link href="/conversation">Go to Conversation</Link>
              </Button>
            </div>
          ) : (
            <div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    <TableHead>Timestamp</TableHead>
                    <TableHead>Ticket</TableHead>
                    <TableHead>Agent</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Eval Results</TableHead>
                    <TableHead className="text-right">Latency</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runRows.map(({ run, session, evals }, idx) => {
                    const isSelected = selectedRunId === run.agent_run_id;
                    const { pass, fail } = countEvals(evals);
                    return (
                      <React.Fragment key={run.agent_run_id}>
                        <motion.tr
                          data-run-id={run.agent_run_id}
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: idx * 0.03, duration: 0.2 }}
                          onClick={() => handleSelectRun(run.agent_run_id)}
                          className={cn(
                            "cursor-pointer transition-colors border-b",
                            isSelected
                              ? "bg-muted/70 hover:bg-muted/70"
                              : "hover:bg-muted/40"
                          )}
                        >
                          <TableCell className="py-2 pl-4 pr-0 w-8">
                            {isSelected ? (
                              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                            ) : (
                              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                            )}
                          </TableCell>
                          <TableCell className="py-2 text-xs font-mono text-muted-foreground">
                            {formatTimestamp(run.created_at)}
                          </TableCell>
                          <TableCell className="py-2 max-w-[160px]">
                            <span className="text-xs truncate block font-mono text-foreground">
                              {run.ticket_id}
                            </span>
                          </TableCell>
                          <TableCell className="py-2">
                            <div className="flex flex-col gap-0.5">
                              <span className="text-xs font-medium">
                                {run.agent_name}
                              </span>
                              <span className="text-[10px] text-muted-foreground font-mono">
                                v{run.agent_version}
                              </span>
                            </div>
                          </TableCell>
                          <TableCell className="py-2">
                            <StatusBadge
                              status={getRunStatusVariant(run.status)}
                              label={run.status}
                            />
                          </TableCell>
                          <TableCell className="py-2">
                            {evals.length === 0 ? (
                              <span className="text-xs text-muted-foreground">
                                —
                              </span>
                            ) : (
                              <div className="flex items-center gap-1.5">
                                <span className="flex items-center gap-0.5 text-xs text-green-600 font-medium">
                                  <CheckCircle2 className="h-3 w-3" />
                                  {pass}
                                </span>
                                <span className="flex items-center gap-0.5 text-xs text-red-600 font-medium">
                                  <XCircle className="h-3 w-3" />
                                  {fail}
                                </span>
                              </div>
                            )}
                          </TableCell>
                          <TableCell className="py-2 text-right font-mono text-xs text-muted-foreground">
                            {formatLatency(run.latency_ms)}
                          </TableCell>
                        </motion.tr>

                        {/* Inline expanded detail row */}
                        {isSelected && (
                          <TableRow className="hover:bg-transparent bg-muted/20">
                            <TableCell
                              colSpan={7}
                              className="p-4 border-b border-dashed"
                            >
                              {loadingEvals ? (
                                <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                                  <RefreshCw className="h-4 w-4 animate-spin" />
                                  Loading evaluations…
                                </div>
                              ) : (
                                <RunDetailPanel
                                  runRow={{ run, session, evals }}
                                  onClose={() => setSelectedRunId(null)}
                                />
                              )}
                            </TableCell>
                          </TableRow>
                        )}
                      </React.Fragment>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
