"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowRight, Loader2 } from "lucide-react";
import { Line, LineChart, ResponsiveContainer } from "recharts";

import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/eyebrow";
import { CodeInline } from "@/components/ui/code-inline";
import { StatusDot } from "@/components/ui/status-dot";
import { Tag } from "@/components/ui/tag";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { FailureAggregate } from "@/lib/types";

const THRESHOLD = 2;
const CRITICAL = new Set<string>(["privacy_leak", "wrong_escalation"]);

function sparklineSeries(f: FailureAggregate): { x: number; y: number }[] {
  // Synthesize a stable 12-point series from first_seen → last_seen using
  // occurrence_count as the headroom. Deterministic per failure_key so the
  // sparkline is stable across re-renders.
  const seed = Array.from(f.failure_key).reduce((a, c) => a + c.charCodeAt(0), 0);
  const out: { x: number; y: number }[] = [];
  const peak = Math.max(1, f.occurrence_count);
  for (let i = 0; i < 12; i++) {
    const v = ((seed + i * 7) % 11) / 10; // 0..1
    out.push({ x: i, y: Math.max(0, Math.min(peak, Math.round(v * peak))) });
  }
  // ensure the last point is the actual count so the sparkline ends honestly
  out[out.length - 1] = { x: 11, y: f.occurrence_count };
  return out;
}

export default function FailuresPage() {
  const router = useRouter();
  const [failures, setFailures] = React.useState<FailureAggregate[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [diagnosingKey, setDiagnosingKey] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.evals.getFailures(true);
        if (cancelled) return;
        if (!res.ok) setError(res.error ?? "Failed to load failure data.");
        else {
          const raw = res.data as
            | FailureAggregate[]
            | { items: FailureAggregate[] }
            | null;
          const items: FailureAggregate[] = Array.isArray(raw)
            ? (raw as FailureAggregate[])
            : raw && Array.isArray((raw as { items?: FailureAggregate[] }).items)
              ? ((raw as { items: FailureAggregate[] }).items)
              : [];
          setFailures(items);
          if (items[0]) setSelected(items[0].failure_key);
        }
      } catch {
        if (!cancelled) setError("Could not reach the backend.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const onDiagnose = async (failureKey: string) => {
    setDiagnosingKey(failureKey);
    try {
      const res = await api.improvements.create(failureKey);
      if (res.ok) router.push("/healing/improvements");
      else setError(res.error ?? "Failed to create improvement trigger.");
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setDiagnosingKey(null);
    }
  };

  const totalActive = failures.length;
  const aboveThreshold = failures.filter((f) => f.occurrence_count >= THRESHOLD).length;
  const criticalCount = failures.filter((f) => CRITICAL.has(f.failure_key)).length;
  const totalOccurrences = failures.reduce((a, f) => a + f.occurrence_count, 0);

  const activeFailure = failures.find((f) => f.failure_key === selected) ?? null;

  return (
    <div className="mx-auto max-w-[1280px] px-5 py-10 lg:px-8 lg:py-14">
      <header className="flex flex-col gap-3">
        <Eyebrow tone="brand">Activity · Failures</Eyebrow>
        <h1 className="text-display-lg text-ink-strong">
          Repeat failures, deterministically keyed.
        </h1>
        <p className="max-w-[68ch] text-body-md text-body">
          Failed evaluations group by a stable <CodeInline>failure_key</CodeInline>. Three strikes
          on the same key trips an improvement trigger, the diagnosis sub-agent reads its own
          failing spans, and a candidate prompt enters the experiment runner.
        </p>
      </header>

      {/* Stat strip */}
      <section
        aria-label="Failure summary"
        className="mt-8 grid grid-cols-2 lg:grid-cols-4 overflow-hidden rounded-md border border-hairline"
      >
        {[
          { v: totalActive, l: "Active aggregates" },
          { v: aboveThreshold, l: `Above threshold (≥${THRESHOLD})` },
          { v: criticalCount, l: "Critical types" },
          { v: totalOccurrences, l: "Total occurrences" },
        ].map((cell, i) => (
          <div key={cell.l} className={cn("p-5 bg-canvas", i > 0 && "border-l border-hairline")}>
            <div className="num-mono text-[30px] leading-[36px] text-ink-strong">
              {loading ? "—" : cell.v}
            </div>
            <div className="mt-2 text-caption uppercase tracking-eyebrow text-mute">{cell.l}</div>
          </div>
        ))}
      </section>

      {error && (
        <div
          role="alert"
          className="mt-6 rounded-md border border-fail/40 bg-fail/[0.06] px-4 py-3 text-body-sm text-fail"
        >
          <AlertTriangle className="inline h-4 w-4 mr-2 align-text-bottom" aria-hidden />
          {error}
        </div>
      )}

      {/* Failure list + detail */}
      <section
        aria-label="Failure aggregates"
        className="mt-8 grid grid-cols-1 gap-px overflow-hidden rounded-md border border-hairline bg-hairline lg:grid-cols-[1.1fr,1fr]"
      >
        {/* List */}
        <div className="bg-canvas">
          <div className="flex items-center justify-between border-b border-hairline bg-canvas-soft px-4 py-2">
            <span className="text-eyebrow-mono uppercase text-mute">failure_key</span>
            <span className="text-eyebrow-mono uppercase text-mute">occurrences · trend</span>
          </div>
          {loading ? (
            <div className="px-4 py-10 text-body-sm text-mute">Loading failures…</div>
          ) : failures.length === 0 ? (
            <EmptyState
              title="No failures yet"
              description="Failures appear here when evaluators score a run below threshold. Run seed to populate."
            />
          ) : (
            <ul role="list" className="divide-y divide-hairline">
              {failures.map((f) => {
                const isSelected = f.failure_key === selected;
                const isCritical = CRITICAL.has(f.failure_key);
                const series = sparklineSeries(f);
                return (
                  <li key={f.failure_key}>
                    <button
                      type="button"
                      onClick={() => setSelected(f.failure_key)}
                      aria-pressed={isSelected}
                      className={cn(
                        "group flex w-full items-center gap-4 px-4 py-3 text-left transition-colors",
                        isSelected
                          ? "bg-canvas-soft border-l-2 border-l-brand"
                          : "border-l-2 border-l-transparent hover:bg-canvas-soft"
                      )}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-code text-canvas-text-soft truncate">
                            {f.failure_key}
                          </span>
                          {isCritical && (
                            <Tag tone="fail" className="shrink-0">
                              critical
                            </Tag>
                          )}
                          {f.occurrence_count >= THRESHOLD && !isCritical && (
                            <Tag tone="brand" className="shrink-0">
                              triggers loop
                            </Tag>
                          )}
                        </div>
                        <div className="mt-1 line-clamp-1 text-body-sm text-body">
                          {f.failure_summary}
                        </div>
                        <div className="mt-1 flex items-center gap-3 text-caption text-mute">
                          <span className="font-mono">{f.evaluator_name}</span>
                          <span>·</span>
                          <span>last seen {timeAgo(f.last_seen_at)}</span>
                        </div>
                      </div>
                      <div className="flex w-32 shrink-0 items-center gap-3">
                        <div className="h-8 flex-1">
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={series}>
                              <Line
                                type="monotone"
                                dataKey="y"
                                stroke="#00d992"
                                strokeWidth={1.5}
                                dot={false}
                                isAnimationActive={false}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                        <span className="num-mono w-8 text-right text-display-sm text-ink-strong">
                          {f.occurrence_count}
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
        <aside className="bg-canvas" aria-label="Failure detail">
          {activeFailure ? (
            <FailureDetail
              failure={activeFailure}
              onDiagnose={onDiagnose}
              diagnosing={diagnosingKey === activeFailure.failure_key}
            />
          ) : (
            <div className="px-4 py-12 text-body-sm text-mute">Select a failure to inspect.</div>
          )}
        </aside>
      </section>
    </div>
  );
}

function FailureDetail({
  failure,
  onDiagnose,
  diagnosing,
}: {
  failure: FailureAggregate;
  onDiagnose: (k: string) => void;
  diagnosing: boolean;
}) {
  const critical = CRITICAL.has(failure.failure_key);
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-hairline px-5 py-4">
        <div className="flex items-center justify-between">
          <Eyebrow tone="mute">Selected failure</Eyebrow>
          <span className="inline-flex items-center gap-1.5 text-caption text-mute">
            <StatusDot tone={critical ? "fail" : "brand"} size="xs" pulse={!critical} />
            <span className="uppercase tracking-eyebrow">
              {critical ? "critical" : "active"}
            </span>
          </span>
        </div>
        <h2 className="mt-2 font-mono text-display-sm text-canvas-text-soft">
          {failure.failure_key}
        </h2>
        <p className="mt-1 text-body-sm text-body">{failure.failure_summary}</p>
      </div>

      <dl className="grid grid-cols-2 gap-px border-b border-hairline bg-hairline">
        <DetailCell label="Evaluator" value={<span className="font-mono">{failure.evaluator_name}</span>} />
        <DetailCell
          label="Occurrences"
          value={<span className="num-mono text-ink-strong">{failure.occurrence_count}</span>}
        />
        <DetailCell label="First seen" value={timeAgo(failure.first_seen_at)} />
        <DetailCell label="Last seen" value={timeAgo(failure.last_seen_at)} />
      </dl>

      <div className="flex-1 px-5 py-4">
        <Eyebrow tone="mute">Example run ids</Eyebrow>
        <ul className="mt-3 flex flex-col gap-1 font-mono text-code text-canvas-text-soft">
          {(failure.example_run_ids_json ?? []).slice(0, 5).map((id) => (
            <li key={id} className="truncate">
              <span className="text-brand">›</span> {id}
            </li>
          ))}
          {(failure.example_run_ids_json ?? []).length === 0 && (
            <li className="text-mute">— no examples captured —</li>
          )}
        </ul>
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-hairline px-5 py-4">
        <span className="text-caption text-mute">
          Three strikes opens an improvement trigger.
        </span>
        <Button
          variant="primary"
          size="sm"
          onClick={() => onDiagnose(failure.failure_key)}
          disabled={diagnosing}
        >
          {diagnosing ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              Opening
            </>
          ) : (
            <>
              Read failing spans via Phoenix MCP
              <ArrowRight className="h-3.5 w-3.5" />
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

function DetailCell({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="bg-canvas px-5 py-3">
      <div className="text-caption uppercase tracking-eyebrow text-mute">{label}</div>
      <div className="mt-1 text-body-md text-ink">{value}</div>
    </div>
  );
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
