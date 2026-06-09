"use client";

import * as React from "react";

import { api } from "@/lib/api";
import type { ReleaseDecision } from "@/lib/types";

export const STAGES = [
  { key: "cycle_started", label: "Cycle started" },
  { key: "seed_started", label: "Seed started" },
  { key: "ticket_created", label: "Tickets created" },
  { key: "agent_run_completed", label: "Agent runs" },
  { key: "evals_completed", label: "Evaluations" },
  { key: "trigger_fired", label: "Failure clustered" },
  { key: "diagnosis_completed", label: "Diagnosis (Phoenix MCP)" },
  { key: "patch_generated", label: "Patch synthesized" },
  { key: "regressions_generated", label: "Regression suite" },
  { key: "experiment_completed", label: "Experiment complete" },
  { key: "release_gate_decided", label: "Release gate verdict" },
] as const;

export type StageKey = (typeof STAGES)[number]["key"];

export type HealingEvent = {
  type: string;
  cycle_id?: string;
  ticket_id?: string;
  agent_run_id?: string;
  improvement_trigger_id?: string;
  failure_key?: string;
  experiment_id?: string;
  baseline_score?: number;
  candidate_score?: number;
  delta?: number;
  decision?: ReleaseDecision;
  decision_id?: string;
  release_score?: number;
  rules_passed?: number;
  phoenix_dataset_id?: string | null;
  count?: number;
  error?: string;
  [k: string]: unknown;
};

interface CycleSnapshot {
  cycleId: string | null;
  failureKey: string | null;
  verdict: ReleaseDecision | null;
  decisionId: string | null;
  baselineScore: number | null;
  candidateScore: number | null;
  experimentId: string | null;
}

interface HealingCycleContextValue extends CycleSnapshot {
  events: HealingEvent[];
  running: boolean;
  modalOpen: boolean;
  dismissWarningOpen: boolean;
  approving: boolean;
  rejecting: boolean;
  startCycle: () => Promise<void>;
  openModal: () => void;
  requestCloseModal: () => void;
  confirmCloseModal: () => void;
  cancelCloseModal: () => void;
  approve: () => Promise<void>;
  reject: () => Promise<void>;
  resetCycle: () => void;
}

const HealingCycleContext = React.createContext<HealingCycleContextValue | null>(
  null,
);

const EMPTY: CycleSnapshot = {
  cycleId: null,
  failureKey: null,
  verdict: null,
  decisionId: null,
  baselineScore: null,
  candidateScore: null,
  experimentId: null,
};

export function HealingCycleProvider({ children }: { children: React.ReactNode }) {
  const [events, setEvents] = React.useState<HealingEvent[]>([]);
  const [running, setRunning] = React.useState(false);
  const [snapshot, setSnapshot] = React.useState<CycleSnapshot>(EMPTY);
  const [modalOpen, setModalOpen] = React.useState(false);
  const [dismissWarningOpen, setDismissWarningOpen] = React.useState(false);
  const [approving, setApproving] = React.useState(false);
  const [rejecting, setRejecting] = React.useState(false);
  const abortRef = React.useRef<AbortController | null>(null);

  React.useEffect(() => {
    // Abort the SSE on unmount so we don't leak the fetch.
    return () => abortRef.current?.abort();
  }, []);

  const handleEvent = React.useCallback((event: HealingEvent) => {
    setEvents((prev) => [...prev, event]);

    switch (event.type) {
      case "cycle_started":
        setSnapshot((s) => ({
          ...s,
          cycleId: (event.cycle_id as string | undefined) ?? null,
        }));
        break;
      case "trigger_fired":
        setSnapshot((s) => ({
          ...s,
          failureKey: (event.failure_key as string | undefined) ?? null,
        }));
        break;
      case "experiment_completed":
        setSnapshot((s) => ({
          ...s,
          experimentId: (event.experiment_id as string | undefined) ?? null,
          baselineScore:
            typeof event.baseline_score === "number" ? event.baseline_score : null,
          candidateScore:
            typeof event.candidate_score === "number" ? event.candidate_score : null,
        }));
        break;
      case "release_gate_decided":
        setSnapshot((s) => ({
          ...s,
          verdict: (event.decision as ReleaseDecision | undefined) ?? null,
          decisionId: (event.decision_id as string | undefined) ?? null,
          failureKey:
            (event.failure_key as string | undefined) ?? s.failureKey,
        }));
        break;
    }
  }, []);

  const startCycle = React.useCallback(async () => {
    if (running) {
      // Already running; just bring the modal up.
      setModalOpen(true);
      return;
    }
    setEvents([]);
    setSnapshot(EMPTY);
    setModalOpen(true);
    setRunning(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      await api.demo.fullLoopStream(
        (e) => handleEvent(e as HealingEvent),
        ctrl.signal,
      );
    } catch (err) {
      const name = (err as { name?: string }).name;
      if (name !== "AbortError") {
        setEvents((prev) => [
          ...prev,
          { type: "error", error: String(err) } as HealingEvent,
        ]);
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }, [running, handleEvent]);

  const openModal = React.useCallback(() => setModalOpen(true), []);

  const requestCloseModal = React.useCallback(() => {
    if (running) {
      setDismissWarningOpen(true);
    } else {
      setModalOpen(false);
    }
  }, [running]);

  const confirmCloseModal = React.useCallback(() => {
    setDismissWarningOpen(false);
    setModalOpen(false);
  }, []);

  const cancelCloseModal = React.useCallback(() => {
    setDismissWarningOpen(false);
  }, []);

  const approve = React.useCallback(async () => {
    if (!snapshot.decisionId) return;
    setApproving(true);
    try {
      await api.releaseGate.approve(
        snapshot.decisionId,
        "demo-user",
        "Approved via Watch it heal modal",
      );
      setSnapshot((s) => ({ ...s, verdict: "promoted" }));
    } catch (err) {
      setEvents((prev) => [
        ...prev,
        {
          type: "error",
          error: `approve failed: ${String(err)}`,
        } as HealingEvent,
      ]);
    } finally {
      setApproving(false);
    }
  }, [snapshot.decisionId]);

  const reject = React.useCallback(async () => {
    if (!snapshot.decisionId) return;
    setRejecting(true);
    try {
      await api.releaseGate.reject(
        snapshot.decisionId,
        "demo-user",
        "Rejected via Watch it heal modal",
      );
      setSnapshot((s) => ({ ...s, verdict: "rejected" }));
    } catch (err) {
      setEvents((prev) => [
        ...prev,
        {
          type: "error",
          error: `reject failed: ${String(err)}`,
        } as HealingEvent,
      ]);
    } finally {
      setRejecting(false);
    }
  }, [snapshot.decisionId]);

  const resetCycle = React.useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setEvents([]);
    setSnapshot(EMPTY);
    setRunning(false);
    setModalOpen(false);
    setDismissWarningOpen(false);
  }, []);

  const value = React.useMemo<HealingCycleContextValue>(
    () => ({
      ...snapshot,
      events,
      running,
      modalOpen,
      dismissWarningOpen,
      approving,
      rejecting,
      startCycle,
      openModal,
      requestCloseModal,
      confirmCloseModal,
      cancelCloseModal,
      approve,
      reject,
      resetCycle,
    }),
    [
      snapshot,
      events,
      running,
      modalOpen,
      dismissWarningOpen,
      approving,
      rejecting,
      startCycle,
      openModal,
      requestCloseModal,
      confirmCloseModal,
      cancelCloseModal,
      approve,
      reject,
      resetCycle,
    ],
  );

  return (
    <HealingCycleContext.Provider value={value}>
      {children}
    </HealingCycleContext.Provider>
  );
}

export function useHealingCycle(): HealingCycleContextValue {
  const ctx = React.useContext(HealingCycleContext);
  if (!ctx) {
    throw new Error("useHealingCycle must be used inside <HealingCycleProvider>");
  }
  return ctx;
}

// Some stages are reached by a failure event instead of the happy-path
// event. Both should mark the stage "reached" so the modal can advance.
// The accompanying failedStages set lets the modal render a fail tone.
const FAIL_TO_STAGE: Record<string, string> = {
  agent_failed: "agent_run_completed",
  evals_failed: "evals_completed",
  aggregation_failed: "trigger_fired",
  experiment_failed: "experiment_completed",
  release_gate_failed: "release_gate_decided",
};

export function reachedStages(events: HealingEvent[]): Set<string> {
  const set = new Set<string>();
  for (const e of events) {
    set.add(e.type);
    const aliased = FAIL_TO_STAGE[e.type];
    if (aliased) set.add(aliased);
  }
  return set;
}

export function failedStages(events: HealingEvent[]): Set<string> {
  const set = new Set<string>();
  for (const e of events) {
    const aliased = FAIL_TO_STAGE[e.type];
    if (aliased) set.add(aliased);
  }
  return set;
}

export function activeStageIndex(events: HealingEvent[]): number {
  const reached = reachedStages(events);
  let lastSeen = -1;
  STAGES.forEach((stage, idx) => {
    if (reached.has(stage.key)) lastSeen = idx;
  });
  return lastSeen;
}
