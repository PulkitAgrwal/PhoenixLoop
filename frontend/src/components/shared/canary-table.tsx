"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Loader2,
  RefreshCw,
  Upload,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/eyebrow";
import { StatusDot } from "@/components/ui/status-dot";
import { CodeInline } from "@/components/ui/code-inline";
import { HairlineDivider } from "@/components/ui/hairline-divider";
import { cn } from "@/lib/utils";

// ─── Types ──────────────────────────────────────────────────────────────────

const JUDGE_LABELS = ["pass", "fail", "insufficient_evidence"] as const;
type JudgeLabel = (typeof JUDGE_LABELS)[number];

interface JudgeKappa {
  judge_name: string;
  judge_model: string;
  n_samples: number;
  cohens_kappa: number | null;
  accuracy: number | null;
  confusion_matrix: Record<string, Record<string, number>> | null;
  computed_at: string | null;
}

interface KappaResponse {
  judges: JudgeKappa[];
  computed_at: string | null;
}

interface ApiEnvelope<T> {
  ok: boolean;
  data: T | null;
  error: string | null;
}

// ─── API ────────────────────────────────────────────────────────────────────

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getKappa(): Promise<ApiEnvelope<KappaResponse>> {
  try {
    const res = await fetch(`${API_URL}/api/evals/canary/kappa`);
    const body = (await res.json()) as ApiEnvelope<KappaResponse>;
    return body;
  } catch (e) {
    return {
      ok: false,
      data: null,
      error: e instanceof Error ? e.message : "Network error",
    };
  }
}

async function postCanary(action: "load" | "run"): Promise<ApiEnvelope<unknown>> {
  try {
    const res = await fetch(`${API_URL}/api/evals/canary/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const body = (await res.json()) as ApiEnvelope<unknown>;
    return body;
  } catch (e) {
    return {
      ok: false,
      data: null,
      error: e instanceof Error ? e.message : "Network error",
    };
  }
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function kappaTone(
  kappa: number | null
): "brand" | "ink" | "fail" | "mute" {
  if (kappa === null || Number.isNaN(kappa)) return "mute";
  if (kappa >= 0.6) return "brand";
  if (kappa >= 0.2) return "ink";
  return "fail";
}

function kappaClass(kappa: number | null): string {
  switch (kappaTone(kappa)) {
    case "brand":
      return "text-brand-soft";
    case "ink":
      return "text-ink";
    case "fail":
      return "text-fail";
    default:
      return "text-mute";
  }
}

function formatPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatKappa(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return value.toFixed(3);
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function labelShort(label: string): string {
  if (label === "insufficient_evidence") return "insuff.";
  return label;
}

// ─── Confusion matrix sub-component ─────────────────────────────────────────

function ConfusionMatrix({
  matrix,
}: {
  matrix: Record<string, Record<string, number>> | null;
}) {
  if (!matrix) {
    return (
      <p className="px-3 py-2 text-body-sm text-mute">
        No confusion matrix recorded yet — run the canary to populate.
      </p>
    );
  }

  return (
    <div className="rounded-md border border-hairline bg-canvas-soft p-3">
      <Eyebrow tone="mute">{"// confusion matrix"}</Eyebrow>
      <div className="mt-2 overflow-x-auto">
        <table className="border-collapse">
          <thead>
            <tr>
              <th className="border border-hairline bg-canvas px-2 py-1 text-left text-caption text-mute">
                <span className="font-mono">expected ↓ / pred →</span>
              </th>
              {JUDGE_LABELS.map((label) => (
                <th
                  key={`col-${label}`}
                  className="border border-hairline bg-canvas px-3 py-1 text-center font-mono text-code text-canvas-text-soft"
                >
                  {labelShort(label)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {JUDGE_LABELS.map((expected) => (
              <tr key={`row-${expected}`}>
                <th
                  scope="row"
                  className="border border-hairline bg-canvas px-2 py-1 text-left font-mono text-code text-mute"
                >
                  {labelShort(expected)}
                </th>
                {JUDGE_LABELS.map((predicted) => {
                  const value = matrix[expected]?.[predicted] ?? 0;
                  const isDiagonal = expected === predicted;
                  return (
                    <td
                      key={`cell-${expected}-${predicted}`}
                      className={cn(
                        "border border-hairline px-3 py-1 text-center font-mono num-mono text-code",
                        isDiagonal
                          ? "text-brand-soft"
                          : value > 0
                            ? "text-fail"
                            : "text-mute"
                      )}
                    >
                      {value}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-caption text-mute">
        Diagonal = agreement with seed labels. Off-diagonal = disagreement.
      </p>
    </div>
  );
}

// ─── Main component ────────────────────────────────────────────────────────

export function CanaryTable() {
  const [data, setData] = React.useState<KappaResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [running, setRunning] = React.useState(false);
  const [loadingFixtures, setLoadingFixtures] = React.useState(false);
  const [actionMessage, setActionMessage] = React.useState<{
    tone: "ok" | "fail";
    text: string;
  } | null>(null);
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());

  const refresh = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    const res = await getKappa();
    if (res.ok && res.data) {
      setData(res.data);
    } else {
      setError(res.error ?? "Failed to load Cohen's kappa");
      setData(null);
    }
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleLoadFixtures = async () => {
    setLoadingFixtures(true);
    setActionMessage(null);
    const res = await postCanary("load");
    setLoadingFixtures(false);
    if (res.ok) {
      setActionMessage({
        tone: "ok",
        text: "Canary fixtures loaded.",
      });
      void refresh();
    } else {
      setActionMessage({
        tone: "fail",
        text: res.error ?? "Failed to load canary fixtures.",
      });
    }
  };

  const handleRecompute = async () => {
    setRunning(true);
    setActionMessage(null);
    const res = await postCanary("run");
    setRunning(false);
    if (res.ok) {
      setActionMessage({
        tone: "ok",
        text: "Canary run complete — Cohen's κ recomputed.",
      });
      void refresh();
    } else {
      setActionMessage({
        tone: "fail",
        text: res.error ?? "Canary run failed.",
      });
    }
  };

  const toggleRow = (judgeName: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(judgeName)) next.delete(judgeName);
      else next.add(judgeName);
      return next;
    });
  };

  const judges = data?.judges ?? [];

  return (
    <section
      aria-label="Judge calibration"
      className="rounded-md border border-hairline bg-canvas overflow-hidden"
    >
      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline bg-canvas-soft px-4 py-3">
        <div className="flex flex-col gap-1">
          <Eyebrow tone="brand">Judge calibration</Eyebrow>
          <p className="text-body-sm text-body">
            Cohen&rsquo;s κ between each LLM judge and seeded canary labels.
            Landis &amp; Koch: κ ≥ 0.6 = substantial agreement.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void handleLoadFixtures()}
            disabled={loadingFixtures || running}
          >
            {loadingFixtures ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Upload className="h-3.5 w-3.5" />
            )}
            {loadingFixtures ? "Loading…" : "Load fixtures"}
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => void handleRecompute()}
            disabled={running || loadingFixtures}
          >
            {running ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            {running ? "Running…" : "Recompute"}
          </Button>
        </div>
      </header>

      {/* Action feedback */}
      <AnimatePresence>
        {actionMessage && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className={cn(
              "flex items-center gap-2 border-b border-hairline px-4 py-2 text-body-sm",
              actionMessage.tone === "ok"
                ? "bg-brand/[0.04] text-brand-soft"
                : "bg-fail/[0.06] text-fail"
            )}
            role="status"
          >
            {actionMessage.tone === "ok" ? (
              <StatusDot tone="brand" size="xs" />
            ) : (
              <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
            )}
            <span>{actionMessage.text}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Table */}
      {loading ? (
        <div className="flex flex-col gap-px bg-hairline">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-12 bg-canvas animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <div className="flex items-center gap-2 px-4 py-4 text-body-sm text-fail">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
          {error}
        </div>
      ) : judges.length === 0 ? (
        <div className="flex flex-col gap-2 px-4 py-6">
          <p className="text-body-sm text-mute">
            No canary κ computed yet. Click{" "}
            <CodeInline>Load fixtures</CodeInline> then{" "}
            <CodeInline>Recompute</CodeInline> to populate.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-canvas-soft text-caption uppercase tracking-eyebrow text-mute">
                <th className="w-8 px-2 py-2.5" aria-hidden />
                <th className="px-3 py-2.5 font-semibold">Judge</th>
                <th className="px-3 py-2.5 font-semibold">Model</th>
                <th className="px-3 py-2.5 font-semibold text-right">N</th>
                <th className="px-3 py-2.5 font-semibold text-right">
                  Accuracy
                </th>
                <th className="px-3 py-2.5 font-semibold text-right">
                  Cohen&rsquo;s κ
                </th>
                <th className="px-3 py-2.5 font-semibold">Last computed</th>
              </tr>
            </thead>
            <tbody>
              {judges.map((j) => {
                const isOpen = expanded.has(j.judge_name);
                return (
                  <React.Fragment key={j.judge_name}>
                    <tr
                      className={cn(
                        "border-t border-hairline transition-colors",
                        "hover:bg-canvas-soft cursor-pointer"
                      )}
                      onClick={() => toggleRow(j.judge_name)}
                      aria-expanded={isOpen}
                    >
                      <td className="px-2 py-2.5 align-middle">
                        {isOpen ? (
                          <ChevronDown className="h-3.5 w-3.5 text-mute" />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5 text-mute" />
                        )}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-code text-canvas-text-soft">
                        {j.judge_name}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-code text-mute">
                        {j.judge_model}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono num-mono text-code text-ink">
                        {j.n_samples}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono num-mono text-code text-ink">
                        {formatPercent(j.accuracy)}
                      </td>
                      <td
                        className={cn(
                          "px-3 py-2.5 text-right font-mono num-mono text-code",
                          kappaClass(j.cohens_kappa)
                        )}
                      >
                        {formatKappa(j.cohens_kappa)}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-code text-mute">
                        {formatTimestamp(j.computed_at)}
                      </td>
                    </tr>
                    <AnimatePresence initial={false}>
                      {isOpen && (
                        <motion.tr
                          key={`${j.judge_name}-expanded`}
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          transition={{ duration: 0.18 }}
                          className="border-t border-hairline"
                        >
                          <td colSpan={7} className="bg-canvas px-4 py-3">
                            <ConfusionMatrix matrix={j.confusion_matrix} />
                          </td>
                        </motion.tr>
                      )}
                    </AnimatePresence>
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <HairlineDivider />

      {/* Footnote */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 text-caption text-mute">
        <span className="font-mono">
          κ tones — brand ≥ 0.60 · ink 0.20–0.60 · fail &lt; 0.20
        </span>
        <span className="font-mono">
          aggregate computed {formatTimestamp(data?.computed_at ?? null)}
        </span>
      </div>
    </section>
  );
}
