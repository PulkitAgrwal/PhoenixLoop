"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  ArrowRight,
  FlaskConical,
  Loader2,
  RefreshCw,
  Zap,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Tag } from "@/components/ui/tag";
import { CodeInline } from "@/components/ui/code-inline";
import { StatusDot } from "@/components/ui/status-dot";
import { EmptyState } from "@/components/shared/empty-state";
import { PhoenixDeepLink } from "@/components/shared/phoenix-deep-link";
import { EvidenceCard } from "@/components/improvements/evidence-card";
import { DiagnosisTrace } from "@/components/improvements/diagnosis-trace";
import { PromptDiff } from "@/components/improvements/prompt-diff";
import { RegressionList } from "@/components/improvements/regression-list";
import { api } from "@/lib/api";
import type {
  FailureAggregate,
  ImprovementTrigger,
  TriggerReason,
} from "@/lib/types";
import { cn } from "@/lib/utils";

type TriggerStatus =
  | "pending"
  | "diagnosed"
  | "regressions_generated"
  | "experiment_complete"
  | "closed";

function statusTone(status: string): "brand" | "warn" | "mute" {
  const s = status as TriggerStatus;
  if (s === "experiment_complete") return "brand";
  if (s === "closed") return "mute";
  return "warn";
}

function statusLabel(status: string): string {
  return status.replace(/_/g, " ");
}

function reasonLabel(reason: TriggerReason): string {
  switch (reason) {
    case "threshold_repeated_failure":
      return "repeat failure";
    case "critical_failure":
      return "critical";
    case "manual_demo_trigger":
      return "manual";
  }
}

function timeAgo(iso: string): string {
  const now = Date.now();
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

interface TriggerDetailProps {
  trigger: ImprovementTrigger;
  onRefresh: () => void;
}

function TriggerDetail({ trigger, onRefresh }: TriggerDetailProps) {
  const router = useRouter();
  const [analyzing, setAnalyzing] = React.useState(false);
  const [generating, setGenerating] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const [actionError, setActionError] = React.useState<string | null>(null);

  const hasDiagnosis =
    trigger.diagnosis_json != null &&
    Object.keys(trigger.diagnosis_json).length > 0;
  const canGenerateRegressions =
    hasDiagnosis &&
    (trigger.regression_examples_json == null ||
      trigger.regression_examples_json.length === 0);
  const canRunExperiment =
    trigger.status !== "experiment_complete" && trigger.status !== "closed";

  const handleAnalyze = async () => {
    setActionError(null);
    setAnalyzing(true);
    try {
      const res = await api.improvements.analyze(trigger.improvement_trigger_id);
      if (!res.ok) setActionError(res.error ?? "Analysis failed");
      else onRefresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Unexpected error");
    } finally {
      setAnalyzing(false);
    }
  };

  const handleGenerateRegressions = async () => {
    setActionError(null);
    setGenerating(true);
    try {
      const res = await api.improvements.generateRegressions(
        trigger.improvement_trigger_id
      );
      if (!res.ok) setActionError(res.error ?? "Generation failed");
      else onRefresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Unexpected error");
    } finally {
      setGenerating(false);
    }
  };

  const handleRunExperiment = async () => {
    setActionError(null);
    setRunning(true);
    try {
      const res = await api.experiments.run(trigger.improvement_trigger_id);
      if (!res.ok) setActionError(res.error ?? "Experiment run failed");
      else router.push("/healing/experiments");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Unexpected error");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          size="sm"
          onClick={handleAnalyze}
          disabled={analyzing}
          aria-label={hasDiagnosis ? "Re-analyze via Phoenix MCP" : "Analyze via Phoenix MCP"}
        >
          {analyzing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
          {analyzing
            ? "Diagnosing…"
            : hasDiagnosis
              ? "Re-diagnose via Phoenix"
              : "Read failing spans via Phoenix MCP"}
        </Button>
        {canGenerateRegressions && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleGenerateRegressions}
            disabled={generating}
          >
            {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />}
            {generating ? "Generating…" : "Generate regressions"}
          </Button>
        )}
        {canRunExperiment && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleRunExperiment}
            disabled={running}
          >
            {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FlaskConical className="h-3.5 w-3.5" />}
            {running ? "Starting…" : "Run experiment"}
            {!running && <ArrowRight className="h-3.5 w-3.5" />}
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={onRefresh} className="ml-auto">
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>

      <AnimatePresence>
        {actionError && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="flex items-center gap-2 rounded-md border border-fail/40 bg-fail/[0.06] px-3 py-2 text-body-sm text-fail"
            role="alert"
          >
            <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
            {actionError}
          </motion.div>
        )}
      </AnimatePresence>

      <EvidenceCard
        exampleRunIds={trigger.example_run_ids_json ?? []}
        failureKey={trigger.failure_key}
      />

      <DiagnosisTrace diagnosis={trigger.diagnosis_json} />

      <PromptDiff proposal={trigger.patch_proposal_json} />

      <RegressionList regressions={trigger.regression_examples_json ?? []} />
    </div>
  );
}

export default function ImprovementsPage() {
  const [triggers, setTriggers] = React.useState<ImprovementTrigger[]>([]);
  const [failuresByKey, setFailuresByKey] = React.useState<
    Record<string, FailureAggregate>
  >({});
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [selectedTrigger, setSelectedTrigger] =
    React.useState<ImprovementTrigger | null>(null);
  const [loadingList, setLoadingList] = React.useState(true);
  const [loadingDetail, setLoadingDetail] = React.useState(false);
  const [listError, setListError] = React.useState<string | null>(null);

  const loadList = React.useCallback(async () => {
    setListError(null);
    setLoadingList(true);
    try {
      const [tRes, fRes] = await Promise.all([
        api.improvements.list(),
        api.evals.getFailures(false),
      ]);
      if (tRes.ok && tRes.data) {
        const raw = tRes.data as
          | ImprovementTrigger[]
          | { items: ImprovementTrigger[] };
        setTriggers(Array.isArray(raw) ? raw : raw.items ?? []);
      } else {
        setListError(tRes.error ?? "Failed to load improvement triggers");
      }
      if (fRes.ok && fRes.data) {
        const fraw = fRes.data as
          | FailureAggregate[]
          | { items: FailureAggregate[] };
        const items = Array.isArray(fraw) ? fraw : fraw.items ?? [];
        const byKey: Record<string, FailureAggregate> = {};
        for (const f of items) byKey[f.failure_key] = f;
        setFailuresByKey(byKey);
      }
    } catch (e) {
      setListError(e instanceof Error ? e.message : "Unexpected error");
    } finally {
      setLoadingList(false);
    }
  }, []);

  React.useEffect(() => {
    loadList();
  }, [loadList]);

  const loadDetail = React.useCallback(
    async (id: string) => {
      setLoadingDetail(true);
      try {
        const res = await api.improvements.get(id);
        if (res.ok && res.data) {
          const raw = res.data as
            | ImprovementTrigger
            | { trigger: ImprovementTrigger };
          const trigger =
            "trigger" in raw && raw.trigger ? raw.trigger : (raw as ImprovementTrigger);
          setSelectedTrigger(trigger);
        }
      } catch {
        const found = triggers.find((t) => t.improvement_trigger_id === id);
        if (found) setSelectedTrigger(found);
      } finally {
        setLoadingDetail(false);
      }
    },
    [triggers]
  );

  React.useEffect(() => {
    if (selectedId === null && triggers[0]) {
      setSelectedId(triggers[0].improvement_trigger_id);
      loadDetail(triggers[0].improvement_trigger_id);
    }
  }, [triggers, selectedId, loadDetail]);

  const handleSelect = (id: string) => {
    setSelectedId(id);
    loadDetail(id);
  };

  const handleRefresh = () => {
    loadList();
    if (selectedId) loadDetail(selectedId);
  };

  return (
    <div className="mx-auto max-w-[1280px] px-5 py-10 lg:px-8 lg:py-14">
      <header className="flex flex-col gap-3">
        <Eyebrow tone="brand">Healing · Improvements</Eyebrow>
        <h1 className="text-display-lg text-ink-strong">
          One trigger. One diagnosis. One patch.
        </h1>
        <p className="max-w-[68ch] text-body-md text-body">
          The diagnosis sub-agent calls Phoenix MCP — <CodeInline>get-spans</CodeInline> and{" "}
          <CodeInline>get-span-annotations</CodeInline> — to read its own failing runs back
          and propose the smallest prompt edit that would close the cluster.
        </p>
      </header>

      <section
        className="mt-8 grid grid-cols-1 gap-px overflow-hidden rounded-md border border-hairline bg-hairline lg:grid-cols-[400px,1fr]"
        aria-label="Improvement triggers"
      >
        <div className="bg-canvas">
          <div className="flex items-center justify-between border-b border-hairline bg-canvas-soft px-4 py-2.5">
            <Eyebrow tone="mute">Triggers</Eyebrow>
            <Button variant="ghost" size="sm" onClick={handleRefresh}>
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </Button>
          </div>

          {loadingList ? (
            <div className="flex flex-col gap-px bg-hairline">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-20 bg-canvas animate-pulse" />
              ))}
            </div>
          ) : listError ? (
            <div className="m-4 rounded-md border border-fail/40 bg-fail/[0.06] px-4 py-3 text-body-sm text-fail">
              <AlertCircle className="inline h-4 w-4 mr-2 align-text-bottom" aria-hidden />
              {listError}
            </div>
          ) : triggers.length === 0 ? (
            <EmptyState
              title="No improvement triggers yet"
              description="Improvement triggers appear when a failure cluster crosses threshold. Run seed."
            />
          ) : (
            <ul role="list" className="divide-y divide-hairline">
              {triggers.map((t) => {
                const isSelected = t.improvement_trigger_id === selectedId;
                const live = failuresByKey[t.failure_key];
                const liveCount = live?.occurrence_count ?? t.occurrence_count;
                const delta = liveCount - t.occurrence_count;
                return (
                  <li key={t.improvement_trigger_id}>
                    <button
                      type="button"
                      onClick={() => handleSelect(t.improvement_trigger_id)}
                      aria-pressed={isSelected}
                      className={cn(
                        "flex w-full flex-col gap-1.5 px-4 py-3 text-left transition-colors",
                        isSelected
                          ? "bg-canvas-soft border-l-2 border-l-brand"
                          : "border-l-2 border-l-transparent hover:bg-canvas-soft"
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-code text-canvas-text-soft truncate">
                          {t.failure_key}
                        </span>
                        <span className="ml-auto inline-flex items-center gap-1.5 text-caption uppercase tracking-eyebrow">
                          <StatusDot tone={statusTone(t.status)} size="xs" />
                          <span
                            className={cn(
                              statusTone(t.status) === "brand" && "text-brand-soft",
                              statusTone(t.status) === "warn" && "text-warn",
                              statusTone(t.status) === "mute" && "text-mute"
                            )}
                          >
                            {statusLabel(t.status)}
                          </span>
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-caption text-mute">
                        <span>{reasonLabel(t.trigger_reason)}</span>
                        <span>·</span>
                        <span>{timeAgo(t.created_at)}</span>
                        <span className="ml-auto inline-flex items-center gap-1.5">
                          <span className="num-mono text-ink">{liveCount}</span>
                          <span className="text-mute">×</span>
                          {delta > 0 && <Tag tone="brand">+{delta} new</Tag>}
                        </span>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Detail */}
        <div className="bg-canvas px-5 py-5 lg:px-7 lg:py-7">
          {!selectedId ? (
            <div className="flex h-full items-center justify-center min-h-[320px]">
              <p className="text-body-sm text-mute">Select a trigger to inspect.</p>
            </div>
          ) : loadingDetail ? (
            <div className="flex flex-col gap-4">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-28 rounded-md border border-hairline bg-canvas-soft animate-pulse"
                />
              ))}
            </div>
          ) : selectedTrigger ? (
            <motion.div
              key={selectedTrigger.improvement_trigger_id}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18 }}
            >
              <div className="mb-5 flex flex-wrap items-end justify-between gap-2 border-b border-hairline pb-4">
                <div>
                  <Eyebrow tone="mute">Selected trigger</Eyebrow>
                  <p className="mt-1 font-mono text-display-sm text-canvas-text-soft">
                    {selectedTrigger.failure_key}
                  </p>
                  <div className="mt-1.5">
                    <PhoenixDeepLink
                      projectName="phoenixloop"
                      label="View failing runs in Phoenix"
                    />
                  </div>
                </div>
                <span className="inline-flex items-center gap-1.5 text-caption uppercase tracking-eyebrow">
                  <StatusDot tone={statusTone(selectedTrigger.status)} size="xs" />
                  <span
                    className={cn(
                      statusTone(selectedTrigger.status) === "brand" && "text-brand-soft",
                      statusTone(selectedTrigger.status) === "warn" && "text-warn",
                      statusTone(selectedTrigger.status) === "mute" && "text-mute"
                    )}
                  >
                    {statusLabel(selectedTrigger.status)}
                  </span>
                </span>
              </div>

              <TriggerDetail trigger={selectedTrigger} onRefresh={handleRefresh} />
            </motion.div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
