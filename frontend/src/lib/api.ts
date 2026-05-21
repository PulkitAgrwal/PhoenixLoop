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

export const api = {
  tickets: {
    list: () => fetchApi("/api/tickets"),
    get: (id: string) => fetchApi(`/api/tickets/${id}`),
    run: (ticketId: string) =>
      fetchApi(`/api/tickets/${ticketId}/run`, { method: "POST" }),
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
  demo: {
    seed: () => fetchApi("/api/demo/seed", { method: "POST" }),
    runAll: () => fetchApi("/api/demo/run-all", { method: "POST" }),
  },
};
