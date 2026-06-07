"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { AlertCircle, ArrowRight, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Tag } from "@/components/ui/tag";
import { StatusDot } from "@/components/ui/status-dot";
import { CodeInline } from "@/components/ui/code-inline";
import { PhoenixDeepLink } from "@/components/shared/phoenix-deep-link";
import { ScoreComparison } from "@/components/experiments/score-comparison";
import { PromptChangesSection } from "@/components/experiments/prompt-changes-section";
import { api } from "@/lib/api";
import type {
  ExperimentRecord,
  ExperimentStatus,
  ReleaseDecision,
  ReleaseGateDecision,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<ExperimentStatus, "brand" | "warn" | "mute" | "fail"> = {
  pending: "warn",
  running: "warn",
  completed: "brand",
  failed: "fail",
};

const VERDICT_TONE: Record<ReleaseDecision, "brand" | "warn" | "mute" | "fail"> = {
  promoted: "brand",
  rejected: "fail",
  pending_human_review: "warn",
  blocked_critical_failure: "fail",
};

const VERDICT_LABEL: Record<ReleaseDecision, string> = {
  promoted: "PROMOTED",
  rejected: "REJECTED",
  pending_human_review: "PENDING REVIEW",
  blocked_critical_failure: "BLOCKED",
};

function fmtDelta(base: number | null, cand: number | null): {
  text: string;
  positive: boolean | null;
} {
  if (base === null || cand === null) return { text: "—", positive: null };
  const delta = (cand - base) * 100;
  return {
    text: `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}`,
    positive: delta >= 0,
  };
}

function timeAgo(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

interface ExperimentDetailData {
  experiment: ExperimentRecord;
  release_gate_decision: ReleaseGateDecision | null;
  baseline_prompt_text: string | null;
  candidate_prompt_text: string | null;
}

export default function ExperimentsPage() {
  const router = useRouter();
  const [experiments, setExperiments] = React.useState<ExperimentRecord[]>([]);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [detail, setDetail] = React.useState<ExperimentDetailData | null>(null);
  const [loadingList, setLoadingList] = React.useState(true);
  const [loadingDetail, setLoadingDetail] = React.useState(false);
  const [listError, setListError] = React.useState<string | null>(null);

  const loadList = React.useCallback(async () => {
    setListError(null);
    setLoadingList(true);
    try {
      const res = await api.experiments.list();
      if (res.ok && res.data) {
        const raw = res.data as ExperimentRecord[] | { items: ExperimentRecord[] };
        setExperiments(Array.isArray(raw) ? raw : raw.items ?? []);
      } else {
        setListError(res.error ?? "Failed to load experiments");
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

  const loadDetail = React.useCallback(async (id: string) => {
    setLoadingDetail(true);
    try {
      const res = await api.experiments.get(id);
      if (res.ok && res.data) setDetail(res.data as ExperimentDetailData);
    } catch {
      /* swallow */
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  React.useEffect(() => {
    if (selectedId === null && experiments[0]) {
      setSelectedId(experiments[0].experiment_id);
      loadDetail(experiments[0].experiment_id);
    }
  }, [experiments, selectedId, loadDetail]);

  const handleSelect = (id: string) => {
    setSelectedId(id);
    setDetail(null);
    loadDetail(id);
  };

  const handleRefresh = () => {
    loadList();
    if (selectedId) loadDetail(selectedId);
  };

  return (
    <div className="mx-auto max-w-[1280px] px-5 py-10 lg:px-8 lg:py-14">
      <header className="flex flex-col gap-3">
        <Eyebrow tone="brand">Healing · Experiments</Eyebrow>
        <h1 className="text-display-lg text-ink-strong">
          Baseline vs candidate. Code-evals only.
        </h1>
        <p className="max-w-[68ch] text-body-md text-body">
          Each experiment scores the baseline and candidate prompts against the regression
          set with deterministic <CodeInline>code_evals</CodeInline> — no LLM judges in the hot
          path. The release gate decides whether the candidate ships.
        </p>
      </header>

      <section
        className="mt-8 grid grid-cols-1 gap-px overflow-hidden rounded-md border border-hairline bg-hairline lg:grid-cols-[420px,1fr]"
        aria-label="Experiments"
      >
        <div className="bg-canvas">
          <div className="flex items-center justify-between border-b border-hairline bg-canvas-soft px-4 py-2.5">
            <Eyebrow tone="mute">Runs</Eyebrow>
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
          ) : experiments.length === 0 ? (
            <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
              <p className="text-body-sm text-body max-w-[40ch]">
                No experiments yet. Create one from the{" "}
                <Link href="/healing/improvements" className="text-brand-soft underline-offset-2 hover:underline">
                  improvements
                </Link>{" "}
                page.
              </p>
            </div>
          ) : (
            <ul role="list" className="divide-y divide-hairline">
              {experiments.map((exp) => {
                const selected = exp.experiment_id === selectedId;
                const delta = fmtDelta(
                  exp.baseline_release_score,
                  exp.candidate_release_score
                );
                const statusTone = STATUS_TONE[exp.status];
                return (
                  <li key={exp.experiment_id}>
                    <button
                      type="button"
                      onClick={() => handleSelect(exp.experiment_id)}
                      aria-pressed={selected}
                      className={cn(
                        "flex w-full flex-col gap-2 px-4 py-3 text-left transition-colors",
                        selected
                          ? "bg-canvas-soft border-l-2 border-l-brand"
                          : "border-l-2 border-l-transparent hover:bg-canvas-soft"
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-code text-canvas-text-soft truncate">
                          {exp.experiment_id.slice(0, 16)}…
                        </span>
                        <span className="ml-auto inline-flex items-center gap-1.5 text-caption uppercase tracking-eyebrow">
                          <StatusDot
                            tone={statusTone}
                            size="xs"
                            pulse={exp.status === "running"}
                          />
                          <span
                            className={cn(
                              statusTone === "brand" && "text-brand-soft",
                              statusTone === "warn" && "text-warn",
                              statusTone === "fail" && "text-fail",
                              statusTone === "mute" && "text-mute"
                            )}
                          >
                            {exp.status}
                          </span>
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-body-sm text-body">
                        <Tag>{exp.baseline_prompt_version}</Tag>
                        <ArrowRight className="h-3 w-3 text-mute" aria-hidden />
                        <Tag tone={delta.positive ? "brand" : "default"}>
                          {exp.candidate_prompt_version}
                        </Tag>
                        <span
                          className={cn(
                            "num-mono ml-auto",
                            delta.positive === true && "text-brand-soft",
                            delta.positive === false && "text-fail",
                            delta.positive === null && "text-mute"
                          )}
                        >
                          {delta.text}
                        </span>
                      </div>
                      <span className="text-caption text-mute">
                        {timeAgo(exp.created_at)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Detail */}
        <div className="bg-canvas px-5 py-5 lg:px-7 lg:py-7 min-h-[640px]">
          <AnimatePresence mode="wait">
            {!selectedId ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex h-full items-center justify-center"
              >
                <p className="text-body-sm text-mute">Select an experiment to view results.</p>
              </motion.div>
            ) : loadingDetail || !detail ? (
              <motion.div
                key="loading"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col gap-4"
              >
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-32 rounded-md border border-hairline bg-canvas-soft animate-pulse"
                  />
                ))}
              </motion.div>
            ) : (
              <motion.div
                key={detail.experiment.experiment_id}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.18 }}
                className="flex flex-col gap-5"
              >
                <header className="flex flex-wrap items-end justify-between gap-4 border-b border-hairline pb-4">
                  <div className="flex flex-col gap-1">
                    <Eyebrow tone="mute">Selected experiment</Eyebrow>
                    <p className="font-mono text-display-sm text-canvas-text-soft">
                      {detail.experiment.experiment_id}
                    </p>
                    <div className="flex items-center gap-3 text-caption text-mute">
                      <span>{timeAgo(detail.experiment.created_at)}</span>
                      <span>·</span>
                      <PhoenixDeepLink experimentId={detail.experiment.experiment_id} />
                    </div>
                  </div>
                  {detail.release_gate_decision && (
                    <VerdictPanel decision={detail.release_gate_decision} />
                  )}
                </header>

                <ScoreComparison experiment={detail.experiment} />

                <PromptChangesSection
                  baseline={detail.baseline_prompt_text}
                  candidate={detail.candidate_prompt_text}
                  baselineVersion={detail.experiment.baseline_prompt_version}
                  candidateVersion={detail.experiment.candidate_prompt_version}
                />

                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => router.push("/healing/release-gate")}
                  >
                    View release gate
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </section>
    </div>
  );
}

function VerdictPanel({ decision }: { decision: ReleaseGateDecision }) {
  const tone = VERDICT_TONE[decision.decision];
  const label = VERDICT_LABEL[decision.decision];
  return (
    <div className="flex flex-col items-end gap-1">
      <Eyebrow tone="mute">Verdict</Eyebrow>
      <div
        className={cn(
          "inline-flex items-center gap-2 rounded-sm border px-3 py-1.5 font-mono text-body-sm font-semibold tracking-wider uppercase",
          tone === "brand" && "border-brand bg-brand/[0.08] text-brand-soft",
          tone === "fail" && "border-fail bg-fail/[0.08] text-fail",
          tone === "warn" && "border-warn bg-warn/[0.08] text-warn",
          tone === "mute" && "border-hairline bg-canvas-soft text-mute"
        )}
      >
        <StatusDot tone={tone} size="xs" />
        {label}
      </div>
      <span className="font-mono text-caption text-mute">
        score{" "}
        <span className="num-mono text-canvas-text-soft">
          {(decision.release_score * 100).toFixed(1)}
        </span>
        {" · "}rules <span className="num-mono">{decision.promotion_rules_passed}</span>
      </span>
    </div>
  );
}
