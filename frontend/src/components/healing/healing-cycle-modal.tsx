"use client";

import * as React from "react";
import { CheckCircle2, Circle, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

import {
  STAGES,
  activeStageIndex,
  reachedStages,
  useHealingCycle,
  type HealingEvent,
} from "./healing-cycle-context";

const PHOENIX_URL = process.env.NEXT_PUBLIC_PHOENIX_URL;

function formatTime(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function shortCycleId(id: string | null): string {
  if (!id) return "—";
  return id.slice(0, 8);
}

function summarizeEvent(e: HealingEvent): string {
  const omit = new Set(["type", "cycle_id", "started_at"]);
  const parts: string[] = [];
  for (const [k, v] of Object.entries(e)) {
    if (omit.has(k)) continue;
    if (v === null || v === undefined) continue;
    if (typeof v === "object") continue;
    parts.push(`${k}=${String(v)}`);
  }
  return parts.join(" · ") || "(no detail)";
}

export function HealingCycleModal() {
  const {
    events,
    running,
    cycleId,
    failureKey,
    verdict,
    baselineScore,
    candidateScore,
    approving,
    rejecting,
    modalOpen,
    requestCloseModal,
    approve,
    reject,
  } = useHealingCycle();

  const logRef = React.useRef<HTMLDivElement | null>(null);

  // Auto-scroll the log to the bottom whenever a new event arrives.
  React.useEffect(() => {
    if (!modalOpen) return;
    const el = logRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [events, modalOpen]);

  const reached = React.useMemo(() => reachedStages(events), [events]);
  const activeIdx = React.useMemo(() => activeStageIndex(events), [events]);

  const startedAtIso = React.useMemo(() => {
    const first = events.find((e) => e.type === "cycle_started");
    return (first?.started_at as string | undefined) ?? null;
  }, [events]);

  function handleOpenChange(open: boolean) {
    if (!open) requestCloseModal();
  }

  return (
    <Dialog open={modalOpen} onOpenChange={handleOpenChange}>
      <DialogContent
        className={cn(
          "w-[min(96vw,960px)] max-w-none gap-0 border-canvas-soft bg-canvas p-0",
          "max-h-[min(90vh,720px)] overflow-hidden text-ink",
        )}
      >
        <header className="flex items-center justify-between border-b border-canvas-soft px-5 py-3">
          <div className="flex flex-col">
            <DialogTitle className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Healing cycle
            </DialogTitle>
            <DialogDescription className="font-mono text-xs text-muted-foreground">
              {shortCycleId(cycleId)} · started {formatTime(startedAtIso)}
            </DialogDescription>
          </div>
        </header>

        <div className="grid grid-cols-1 gap-0 sm:grid-cols-[2fr_3fr]">
          {/* Stages column */}
          <ol
            className="border-r-0 border-canvas-soft p-5 sm:border-r"
            aria-live="polite"
          >
            {STAGES.map((stage, idx) => {
              const done = reached.has(stage.key);
              const active = !done && running && idx === activeIdx + 1;
              return (
                <li
                  key={stage.key}
                  className="flex items-start gap-3 py-1.5 text-sm"
                >
                  <span className="mt-0.5">
                    {done ? (
                      <CheckCircle2 className="h-4 w-4 text-brand" />
                    ) : active ? (
                      <Loader2
                        className="h-4 w-4 animate-spin text-brand motion-reduce:animate-none"
                        aria-label="in progress"
                      />
                    ) : (
                      <Circle className="h-4 w-4 text-muted-foreground/40" />
                    )}
                  </span>
                  <span
                    className={cn(
                      "leading-tight",
                      done
                        ? "text-ink"
                        : active
                          ? "text-ink"
                          : "text-muted-foreground",
                    )}
                  >
                    {stage.label}
                  </span>
                </li>
              );
            })}
          </ol>

          {/* Live log column */}
          <div
            ref={logRef}
            className="max-h-[420px] overflow-y-auto bg-canvas-soft/40 px-5 py-4 font-mono text-[11px] leading-relaxed text-muted-foreground"
          >
            {events.length === 0 ? (
              <div className="text-muted-foreground/60">
                Waiting for first event…
              </div>
            ) : (
              events.map((e, i) => (
                <div key={i} className="py-0.5">
                  <span className="text-ink/70">
                    {formatTime(new Date().toISOString())}
                  </span>{" "}
                  <span className="text-brand">{e.type}</span>{" "}
                  <span>{summarizeEvent(e)}</span>
                </div>
              ))
            )}
          </div>
        </div>

        <footer className="border-t border-canvas-soft px-5 py-4">
          <VerdictFooter
            verdict={verdict}
            running={running}
            baselineScore={baselineScore}
            candidateScore={candidateScore}
            failureKey={failureKey}
            approving={approving}
            rejecting={rejecting}
            onApprove={approve}
            onReject={reject}
            onClose={requestCloseModal}
          />
        </footer>
      </DialogContent>
    </Dialog>
  );
}

interface VerdictFooterProps {
  verdict: string | null;
  running: boolean;
  baselineScore: number | null;
  candidateScore: number | null;
  failureKey: string | null;
  approving: boolean;
  rejecting: boolean;
  onApprove: () => void;
  onReject: () => void;
  onClose: () => void;
}

function VerdictFooter({
  verdict,
  running,
  baselineScore,
  candidateScore,
  failureKey,
  approving,
  rejecting,
  onApprove,
  onReject,
  onClose,
}: VerdictFooterProps) {
  const phoenixHref = phoenixDeepLink(failureKey);

  if (verdict === "pending_human_review") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Candidate passed the release gate but is held for human review.
        </p>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onReject}
            disabled={rejecting || approving}
          >
            {rejecting ? "Rejecting…" : "Reject"}
          </Button>
          <Button
            size="sm"
            onClick={onApprove}
            disabled={approving || rejecting}
          >
            {approving ? "Promoting…" : "Approve & promote →"}
          </Button>
        </div>
      </div>
    );
  }

  if (verdict === "promoted") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm">
          <span className="text-brand">✓</span> Promoted —{" "}
          <span className="font-mono text-xs">
            {scoreLabel(baselineScore)} → {scoreLabel(candidateScore)}
          </span>
        </p>
        {phoenixHref ? (
          <Button asChild size="sm" variant="outline">
            <a href={phoenixHref} target="_blank" rel="noreferrer">
              View full cycle in Phoenix →
            </a>
          </Button>
        ) : null}
      </div>
    );
  }

  if (verdict === "rejected") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          <span className="text-danger">✗</span> Candidate rejected. Production
          prompt unchanged.
        </p>
        <Button size="sm" variant="outline" onClick={onClose}>
          Close
        </Button>
      </div>
    );
  }

  // No verdict yet → still running, or pre-trigger.
  return (
    <div className="flex items-center justify-between text-xs text-muted-foreground">
      <span>
        {running
          ? "Cycle in progress — close to send to background chip."
          : "Waiting on cycle…"}
      </span>
    </div>
  );
}

function scoreLabel(score: number | null): string {
  return score === null ? "—" : score.toFixed(2);
}

function phoenixDeepLink(failureKey: string | null): string | null {
  if (!PHOENIX_URL) return null;
  if (!failureKey) return PHOENIX_URL;
  return `${PHOENIX_URL.replace(/\/$/, "")}/prompts`;
}
