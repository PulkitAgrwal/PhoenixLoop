"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { AlertCircle, FileText, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { TableSkeleton } from "@/components/shared/loading-skeleton";
import { VersionList } from "@/components/prompts/version-list";
import { VersionDetail } from "@/components/prompts/version-detail";
import { EditPromptDialog } from "@/components/prompts/edit-prompt-dialog";
import { SaveMode } from "@/components/prompts/confirm-save-dialog";
import { api } from "@/lib/api";
import { Prompt, PromptVersion } from "@/lib/types";

const IDENTIFIER = "support-agent";

export default function PromptsPage() {
  const router = useRouter();
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [experimentLoading, setExperimentLoading] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const pRes = await api.prompts.get(IDENTIFIER);
      if (!pRes.ok || !pRes.data) {
        setError(pRes.error ?? "Failed to load prompt");
        return;
      }
      const p = pRes.data as Prompt;
      setPrompt(p);

      const vRes = await api.prompts.listVersions(IDENTIFIER);
      if (!vRes.ok || !vRes.data) {
        setError(vRes.error ?? "Failed to load versions");
        return;
      }
      const items =
        (vRes.data as { items: PromptVersion[] }).items ?? [];
      setVersions(items);

      // Default-select the active version on first load
      setSelectedId((prev) => {
        if (prev && items.some((v) => v.prompt_version_id === prev)) return prev;
        const active = items.find(
          (v) => v.prompt_version_id === p.active_version_id,
        );
        return active?.prompt_version_id ?? items[0]?.prompt_version_id ?? null;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const selected =
    versions.find((v) => v.prompt_version_id === selectedId) ?? null;
  const isActive = selected?.prompt_version_id === prompt?.active_version_id;

  async function handleSave({
    promptText,
    description,
    mode,
  }: {
    promptText: string;
    description?: string;
    mode: SaveMode;
  }) {
    const res = await api.prompts.createVersion(IDENTIFIER, {
      prompt_text: promptText,
      description,
    });
    if (!res.ok || !res.data) throw new Error(res.error ?? "Create failed");
    const newVersionId = (res.data as PromptVersion).prompt_version_id;
    if (mode === "experiment") {
      const expRes = await api.prompts.launchExperiment(
        IDENTIFIER,
        newVersionId,
      );
      if (!expRes.ok || !expRes.data)
        throw new Error(expRes.error ?? "Experiment launch failed");
      await loadAll();
      router.push(`/healing/experiments`);
    } else {
      await loadAll();
      setSelectedId(newVersionId);
    }
  }

  async function handleLaunchExperiment(versionId: string) {
    setExperimentLoading(true);
    setError(null);
    try {
      const res = await api.prompts.launchExperiment(IDENTIFIER, versionId);
      if (res.ok && res.data) {
        router.push(`/healing/experiments`);
      } else {
        setError(res.error ?? "Failed to launch experiment");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to launch experiment");
    } finally {
      setExperimentLoading(false);
    }
  }

  // Source the "active" version object for the Edit dialog. We always want
  // to edit the active prompt, regardless of which version is selected.
  const activeVersion =
    versions.find(
      (v) => v.prompt_version_id === prompt?.active_version_id,
    ) ?? null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <FileText className="h-5 w-5 text-muted-foreground" />
            Prompts
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Version history and live editor for the support agent&apos;s system
            prompt.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={loadAll}
          disabled={loading}
          className="gap-2"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`}
          />
          Refresh
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr]">
        <div className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Versions ({versions.length})
          </h2>
          {loading ? (
            <TableSkeleton rows={3} />
          ) : (
            <VersionList
              versions={versions}
              activeVersionId={prompt?.active_version_id ?? null}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          )}
        </div>

        <div>
          <AnimatePresence mode="wait">
            {!selected ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex h-[320px] items-center justify-center rounded-lg border border-dashed text-muted-foreground"
              >
                Select a version to view details
              </motion.div>
            ) : (
              <motion.div
                key={selected.prompt_version_id}
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.2 }}
              >
                <VersionDetail
                  version={selected}
                  isActive={isActive}
                  onEdit={() => setEditOpen(true)}
                  onLaunchExperiment={() =>
                    handleLaunchExperiment(selected.prompt_version_id)
                  }
                  experimentLoading={experimentLoading}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {activeVersion && (
        <EditPromptDialog
          open={editOpen}
          onClose={() => setEditOpen(false)}
          activeVersion={activeVersion}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
