"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";

interface PromptVersionRow {
  prompt_version_id: string;
  version_tag: string;
}

interface PromptRow {
  prompt_identifier: string;
  active_version_id: string | null;
  description: string | null;
}

interface PaginatedItems<T> {
  items: T[];
}

export interface ActivePromptInfo {
  promptName: string;
  versionLabel: string;
  versionId: string;
}

export function useActivePrompt() {
  const [info, setInfo] = useState<ActivePromptInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const list = await api.prompts.list();
        if (!list.ok || !list.data) {
          if (!cancelled) setError(list.error ?? "Failed to list prompts");
          return;
        }
        const prompts =
          (list.data as PaginatedItems<PromptRow>).items ?? [];
        if (prompts.length === 0) {
          if (!cancelled) setError("No prompts registered");
          return;
        }
        const target = prompts[0];
        if (!target.active_version_id) {
          if (!cancelled) setError("Prompt has no active version");
          return;
        }
        const versions = await api.prompts.listVersions(
          target.prompt_identifier,
        );
        if (!versions.ok || !versions.data) {
          if (!cancelled)
            setError(versions.error ?? "Failed to list versions");
          return;
        }
        const vlist =
          (versions.data as PaginatedItems<PromptVersionRow>).items ?? [];
        const active = vlist.find(
          (v) => v.prompt_version_id === target.active_version_id,
        );
        if (!active) {
          if (!cancelled) setError("No active version");
          return;
        }
        if (!cancelled) {
          setInfo({
            promptName: target.prompt_identifier,
            versionLabel: active.version_tag,
            versionId: active.prompt_version_id,
          });
        }
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Load failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return { info, loading, error };
}
