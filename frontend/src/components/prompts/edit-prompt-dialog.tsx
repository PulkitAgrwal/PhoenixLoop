"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { PromptDiffView } from "./prompt-diff-view";
import { ConfirmSaveDialog, SaveMode } from "./confirm-save-dialog";
import { PromptVersion } from "@/lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
  activeVersion: PromptVersion;
  onSave: (params: {
    promptText: string;
    description?: string;
    mode: SaveMode;
  }) => Promise<void>;
}

export function EditPromptDialog({
  open,
  onClose,
  activeVersion,
  onSave,
}: Props) {
  const [text, setText] = useState(activeVersion.prompt_text);
  const [description, setDescription] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset local state when the dialog re-opens against a different version.
  useEffect(() => {
    if (open) {
      setText(activeVersion.prompt_text);
      setDescription("");
      setError(null);
    }
  }, [open, activeVersion.prompt_text]);

  const stats = useMemo(() => {
    const charCount = text.length;
    const baseLines = activeVersion.prompt_text.split("\n").length;
    const editedLines = text.split("\n").length;
    return { charCount, lineDelta: editedLines - baseLines };
  }, [text, activeVersion.prompt_text]);

  const isUnchanged = text === activeVersion.prompt_text;
  const isInvalid = text.length === 0 || text.length > 200_000;

  async function handleConfirm(mode: SaveMode) {
    setSaving(true);
    setError(null);
    try {
      await onSave({
        promptText: text,
        description: description || undefined,
        mode,
      });
      setConfirmOpen(false);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o && !saving) onClose();
      }}
    >
      <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col gap-3">
        <DialogHeader>
          <DialogTitle>
            Edit Prompt — {activeVersion.prompt_identifier}
          </DialogTitle>
          <DialogDescription>
            Editing creates a new version. The active prompt does not change
            until an experiment promotes it.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="edited" className="flex-1 flex flex-col min-h-0">
          <TabsList className="self-start">
            <TabsTrigger value="edited">Edited</TabsTrigger>
            <TabsTrigger value="original">Original</TabsTrigger>
            <TabsTrigger value="diff">Diff</TabsTrigger>
          </TabsList>

          <TabsContent value="edited" className="flex-1 min-h-0">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="w-full h-[50vh] p-3 font-mono text-xs bg-transparent border rounded-md resize-none outline-none focus:ring-2 focus:ring-ring"
              spellCheck={false}
            />
          </TabsContent>

          <TabsContent value="original" className="flex-1 min-h-0">
            <ScrollArea className="h-[50vh] rounded-md border bg-muted/20 p-3">
              <pre className="font-mono text-xs whitespace-pre-wrap break-words">
                {activeVersion.prompt_text}
              </pre>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="diff" className="flex-1 min-h-0">
            <PromptDiffView
              baseline={activeVersion.prompt_text}
              candidate={text}
              showCopy={false}
            />
          </TabsContent>
        </Tabs>

        <div className="text-xs text-muted-foreground tabular-nums">
          {stats.charCount.toLocaleString()} chars
          {stats.lineDelta !== 0 &&
            ` · ${stats.lineDelta > 0 ? "+" : ""}${stats.lineDelta} lines`}
          {text.length > 200_000 && (
            <span className="text-red-600 ml-2">Exceeds 200,000 chars</span>
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="description">Description (optional)</Label>
          <Input
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What's changed in this version?"
            maxLength={2000}
          />
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button
            onClick={() => setConfirmOpen(true)}
            disabled={isUnchanged || isInvalid || saving}
          >
            Save as new version →
          </Button>
        </DialogFooter>

        <ConfirmSaveDialog
          open={confirmOpen}
          parentVersionTag={activeVersion.version_tag}
          onCancel={() => setConfirmOpen(false)}
          onConfirm={handleConfirm}
          loading={saving}
        />
      </DialogContent>
    </Dialog>
  );
}
