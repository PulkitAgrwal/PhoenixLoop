import type { CreatePromptVersionPayload } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchApi<T>(
  path: string,
  options?: RequestInit,
): Promise<{ ok: boolean; data: T | null; error: string | null }> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  return res.json();
}

export type StreamEvent =
  | { type: "agent_start"; agent_run_id: string; session_id: string }
  | { type: "tool_call_started"; index: number; tool_name: string; input: Record<string, unknown> }
  | {
      type: "tool_call_completed";
      index: number;
      tool_name: string;
      output: Record<string, unknown>;
      status: string;
      latency_ms: number | null;
    }
  | { type: "text_chunk"; text: string }
  | { type: "agent_done"; agent_run: Record<string, unknown> }
  | { type: "eval_result"; result: Record<string, unknown> }
  | { type: "done"; triggers_created: number }
  | { type: "error"; error: string };

export async function runTicketStream(
  ticketId: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/api/tickets/${ticketId}/run/stream`, {
    method: "POST",
    headers: { Accept: "text/event-stream" },
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`stream failed: HTTP ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line. Within a frame, one or
    // more lines may start with "data: ".
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      for (const line of frame.split("\n")) {
        if (line.startsWith("data: ")) {
          const json = line.slice(6);
          try {
            onEvent(JSON.parse(json) as StreamEvent);
          } catch {
            // ignore malformed frames
          }
        }
      }
    }
  }
}

export const api = {
  tickets: {
    list: () => fetchApi("/api/tickets"),
    get: (id: string) => fetchApi(`/api/tickets/${id}`),
    run: (ticketId: string) =>
      fetchApi(`/api/tickets/${ticketId}/run`, { method: "POST" }),
    runStream: runTicketStream,
  },
  conversations: {
    list: () => fetchApi("/api/conversations"),
    get: (id: string) => fetchApi(`/api/conversations/${id}`),
  },
  evals: {
    getForRun: (runId: string) => fetchApi(`/api/evals/${runId}`),
    getFailures: (activeOnly?: boolean) =>
      fetchApi(`/api/failures?active_only=${activeOnly ?? true}`),
  },
  improvements: {
    list: () => fetchApi("/api/improvements"),
    get: (id: string) => fetchApi(`/api/improvements/${id}`),
    create: (failureKey: string) =>
      fetchApi("/api/improvements", {
        method: "POST",
        body: JSON.stringify({ failure_key: failureKey }),
      }),
    analyze: (triggerId: string) =>
      fetchApi(`/api/improvements/${triggerId}/actions/analyze`, {
        method: "POST",
      }),
    generateRegressions: (triggerId: string) =>
      fetchApi(`/api/improvements/${triggerId}/actions/generate-regressions`, {
        method: "POST",
      }),
  },
  experiments: {
    list: () => fetchApi("/api/experiments"),
    get: (id: string) => fetchApi(`/api/experiments/${id}`),
    run: (triggerId: string) =>
      fetchApi("/api/experiments", {
        method: "POST",
        body: JSON.stringify({ improvement_trigger_id: triggerId }),
      }),
  },
  releaseGate: {
    list: () => fetchApi("/api/release-gate"),
    get: (decisionId: string) =>
      fetchApi(`/api/release-gate/${decisionId}`),
    approve: (decisionId: string, reviewerId: string, comment: string) =>
      fetchApi(`/api/release-gate/${decisionId}/actions/approve`, {
        method: "POST",
        body: JSON.stringify({ reviewer_id: reviewerId, comment }),
      }),
    reject: (decisionId: string, reviewerId: string, comment: string) =>
      fetchApi(`/api/release-gate/${decisionId}/actions/reject`, {
        method: "POST",
        body: JSON.stringify({ reviewer_id: reviewerId, comment }),
      }),
  },
  healing: {
    cycle: (failureKey: string) =>
      fetchApi<import("@/lib/types").HealingCycle>(
        `/api/healing/cycles/${encodeURIComponent(failureKey)}`,
      ),
  },
  demo: {
    seed: () => fetchApi("/api/demo/seed", { method: "POST" }),
    runAll: () => fetchApi("/api/demo/run-all", { method: "POST" }),
    fullLoop: () => fetchApi("/api/demo/full-loop", { method: "POST" }),
    fullLoopStream: async (
      onEvent: (e: { type: string; [k: string]: unknown }) => void,
      signal?: AbortSignal,
    ): Promise<void> => {
      const res = await fetch(`${API_URL}/api/demo/full-loop/stream`, {
        method: "POST",
        headers: { Accept: "text/event-stream" },
        signal,
      });
      if (!res.ok || !res.body) {
        throw new Error(`stream failed: HTTP ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          for (const line of frame.split("\n")) {
            if (line.startsWith("data: ")) {
              try {
                onEvent(JSON.parse(line.slice(6)));
              } catch {
                // ignore
              }
            }
          }
        }
      }
    },
  },
  activity: {
    list: (limit = 5) => fetchApi(`/api/activity?limit=${limit}`),
  },
  config: {
    get: () => fetchApi("/api/config"),
  },
  health: {
    check: () => fetchApi("/api/health"),
  },
  stats: {
    get: () =>
      fetchApi<{
        agent_runs_traced: number;
        evaluators_wired: number;
        mcp_tool_calls_per_run_avg: number;
        prompts_auto_promoted: number;
        baseline_avg_score: number | null;
        post_heal_avg_score: number | null;
        delta_pct: number | null;
        auto_promoted_regression_count: number;
      }>("/api/stats"),
  },
  prompts: {
    list: () => fetchApi("/api/prompts"),
    get: (id: string) => fetchApi(`/api/prompts/${id}`),
    listVersions: (id: string) =>
      fetchApi(`/api/prompts/${id}/versions?page_size=200`),
    getVersion: (id: string, versionId: string) =>
      fetchApi(`/api/prompts/${id}/versions/${versionId}`),
    createVersion: (id: string, payload: CreatePromptVersionPayload) =>
      fetchApi(`/api/prompts/${id}/versions`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    launchExperiment: (id: string, versionId: string) =>
      fetchApi(`/api/prompts/${id}/versions/${versionId}/actions/experiment`, {
        method: "POST",
      }),
  },
};
