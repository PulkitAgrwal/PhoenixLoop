"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FlaskConical,
  GitCommit,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { api } from "@/lib/api";
import type { HealingCycle } from "@/lib/types";
import { PhoenixDeepLink } from "@/components/shared/phoenix-deep-link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type Stage = {
  key: string;
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  status: "done" | "active" | "pending";
  detail: React.ReactNode;
  timestamp?: string;
};

function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function buildStages(cycle: HealingCycle): Stage[] {
  const agg = cycle.failure_aggregates[0];
  const trigger = cycle.latest_trigger;
  const experiment = cycle.experiments[cycle.experiments.length - 1] ?? null;
  const decision = cycle.release_gate_decision;
  const approval = cycle.human_approval;

  const stages: Stage[] = [
    {
      key: "failure",
      title: "Failure detected",
      icon: AlertCircle,
      status: agg ? "done" : "pending",
      detail: agg
        ? `${agg.occurrence_count} occurrences · evaluator ${agg.evaluator_name}`
        : "No aggregate found",
      timestamp: agg?.last_seen_at,
    },
    {
      key: "aggregate",
      title: "Cluster crossed threshold",
      icon: Search,
      status: trigger ? "done" : "pending",
      detail: trigger
        ? `Trigger ${trigger.improvement_trigger_id.slice(0, 8)}… (${trigger.trigger_reason})`
        : "No trigger fired yet",
      timestamp: trigger?.created_at,
    },
    {
      key: "diagnosis",
      title: "Diagnosis (Phoenix MCP)",
      icon: Sparkles,
      status: trigger?.diagnosis_json ? "done" : trigger ? "active" : "pending",
      detail: trigger?.diagnosis_json ? (
        <div className="space-y-1">
          <div>
            Root cause:{" "}
            <span className="font-medium">
              {String(trigger.diagnosis_json.root_cause ?? "—")}
            </span>
          </div>
          <div className="text-muted-foreground">
            Confidence:{" "}
            {String(trigger.diagnosis_json.confidence ?? "—")}
          </div>
        </div>
      ) : (
        "Awaiting diagnosis"
      ),
      timestamp: trigger?.updated_at,
    },
    {
      key: "patch",
      title: "Patch synthesized",
      icon: GitCommit,
      status: trigger?.patch_proposal_json ? "done" : "pending",
      detail: trigger?.patch_proposal_json ? (
        <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-muted/40 p-2 text-xs">
          {String(trigger.patch_proposal_json.proposed_change ?? "—")}
        </pre>
      ) : (
        "No patch yet"
      ),
    },
    {
      key: "experiment",
      title: "Experiment (baseline vs candidate)",
      icon: FlaskConical,
      status: experiment ? "done" : "pending",
      detail: experiment ? (
        <div className="space-y-1">
          <div>
            Score: {experiment.baseline_release_score?.toFixed(3)} →{" "}
            {experiment.candidate_release_score?.toFixed(3)}
          </div>
          <div className="flex gap-2 pt-1">
            <PhoenixDeepLink
              experimentId={experiment.phoenix_experiment_id_baseline ?? undefined}
              label="Baseline in Phoenix"
            />
            <PhoenixDeepLink
              experimentId={experiment.phoenix_experiment_id_candidate ?? undefined}
              label="Candidate in Phoenix"
            />
          </div>
        </div>
      ) : (
        "No experiment yet"
      ),
      timestamp: experiment?.completed_at ?? undefined,
    },
    {
      key: "release_gate",
      title: "Release gate verdict",
      icon: ShieldCheck,
      status: decision ? "done" : "pending",
      detail: decision ? (
        <div>
          <Badge>{decision.decision}</Badge>{" "}
          {decision.promotion_rules_passed}/6 rules · score{" "}
          {decision.release_score?.toFixed(3)}
        </div>
      ) : (
        "No verdict yet"
      ),
      timestamp: decision?.decided_at,
    },
    {
      key: "approval",
      title: "Human approval",
      icon: CheckCircle2,
      status: approval ? "done" : decision ? "active" : "pending",
      detail: approval
        ? `${approval.status} by ${approval.reviewer_id}`
        : decision?.decision === "pending_human_review"
          ? "Awaiting reviewer click"
          : "—",
      timestamp: approval?.reviewed_at ?? undefined,
    },
  ];
  return stages;
}

export default function HealingCyclePage() {
  const params = useParams<{ failure_key: string }>();
  const failureKey = decodeURIComponent(params.failure_key);
  const [cycle, setCycle] = React.useState<HealingCycle | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      const res = await api.healing.cycle(failureKey);
      if (cancelled) return;
      if (res.ok && res.data) {
        setCycle(res.data as HealingCycle);
      } else {
        setError(res.error ?? "Unknown error");
      }
      setLoading(false);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [failureKey]);

  if (loading) return <div className="p-8">Loading healing cycle…</div>;
  if (error || !cycle)
    return <div className="p-8 text-destructive">Error: {error}</div>;

  const stages = buildStages(cycle);

  return (
    <div className="container max-w-3xl space-y-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold">Healing Cycle</h1>
        <p className="text-sm text-muted-foreground">
          Failure key:{" "}
          <span className="font-mono text-foreground">{failureKey}</span>
        </p>
      </div>

      <div className="space-y-3">
        {stages.map((stage, idx) => {
          const Icon = stage.icon;
          return (
            <motion.div
              key={stage.key}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.05, duration: 0.2 }}
            >
              <Card
                className={
                  stage.status === "done"
                    ? "border-l-4 border-l-emerald-500"
                    : stage.status === "active"
                      ? "border-l-4 border-l-amber-500"
                      : "border-l-4 border-l-muted"
                }
              >
                <CardHeader className="flex flex-row items-start justify-between gap-3 py-3">
                  <div className="flex items-start gap-3">
                    <Icon className="mt-0.5 h-5 w-5 text-muted-foreground" />
                    <div>
                      <CardTitle className="text-base">{stage.title}</CardTitle>
                      {stage.timestamp && (
                        <p className="text-xs text-muted-foreground">
                          <Clock className="mr-1 inline h-3 w-3" />
                          {fmtTime(stage.timestamp)}
                        </p>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-0 text-sm">
                  {stage.detail}
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
