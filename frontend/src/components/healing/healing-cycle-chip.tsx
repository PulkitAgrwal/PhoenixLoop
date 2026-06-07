"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

import {
  STAGES,
  activeStageIndex,
  useHealingCycle,
} from "./healing-cycle-context";

export function HealingCycleChip() {
  const { events, running, cycleId, verdict, modalOpen, openModal } =
    useHealingCycle();

  // Only show when there's a cycle to track AND the modal is closed.
  const hasCycle = cycleId !== null || verdict !== null || running;
  if (!hasCycle || modalOpen) return null;

  const idx = activeStageIndex(events);
  const reachedCount = idx + 1;
  const totalStages = STAGES.length;

  const isComplete = !running && verdict !== null;
  const label = isComplete
    ? labelForVerdict(verdict)
    : `Healing cycle · stage ${reachedCount}/${totalStages} · open`;

  return (
    <button
      type="button"
      onClick={openModal}
      className={cn(
        "fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-md border border-canvas-soft bg-canvas-soft/95 px-3 py-2 text-xs font-medium text-ink shadow-lg backdrop-blur",
        "transition-colors hover:bg-canvas-soft",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
      )}
      aria-label="Open healing cycle modal"
    >
      <Dot complete={isComplete} verdict={verdict} />
      <span>{label}</span>
    </button>
  );
}

function Dot({
  complete,
  verdict,
}: {
  complete: boolean;
  verdict: string | null;
}) {
  if (complete && verdict === "rejected") {
    return <span className="h-2 w-2 rounded-full bg-danger" aria-hidden />;
  }
  if (complete) {
    return <span className="h-2 w-2 rounded-full bg-brand" aria-hidden />;
  }
  return (
    <span className="relative flex h-2 w-2" aria-hidden>
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand opacity-70 motion-reduce:animate-none" />
      <span className="relative inline-flex h-2 w-2 rounded-full bg-brand" />
    </span>
  );
}

function labelForVerdict(verdict: string | null): string {
  if (verdict === "promoted") return "Cycle complete · view promotion →";
  if (verdict === "rejected") return "Cycle complete · rejected · view →";
  if (verdict === "pending_human_review")
    return "Awaiting review · view →";
  return "Cycle complete · view →";
}
