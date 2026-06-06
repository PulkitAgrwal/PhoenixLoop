"use client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { useState } from "react";

export type SaveMode = "draft" | "experiment";

interface Props {
  open: boolean;
  parentVersionTag: string;
  onCancel: () => void;
  onConfirm: (mode: SaveMode) => void;
  loading: boolean;
}

export function ConfirmSaveDialog({
  open,
  parentVersionTag,
  onCancel,
  onConfirm,
  loading,
}: Props) {
  const [mode, setMode] = useState<SaveMode>("experiment");

  return (
    <AlertDialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onCancel();
      }}
    >
      <AlertDialogContent className="max-w-lg">
        <AlertDialogHeader>
          <AlertDialogTitle>Create new version?</AlertDialogTitle>
          <AlertDialogDescription>
            This will create a new version descended from{" "}
            <span className="font-mono">{parentVersionTag}</span>. What should
            we do with it?
          </AlertDialogDescription>
        </AlertDialogHeader>

        <RadioGroup
          value={mode}
          onValueChange={(v) => setMode(v as SaveMode)}
          className="space-y-3 my-3"
        >
          <div className="flex items-start space-x-2">
            <RadioGroupItem id="mode-draft" value="draft" className="mt-1" />
            <div>
              <Label htmlFor="mode-draft" className="font-medium">
                Save as draft
              </Label>
              <p className="text-xs text-muted-foreground">
                Creates the version but doesn&apos;t change what the agent
                uses. You can experiment on it later.
              </p>
            </div>
          </div>
          <div className="flex items-start space-x-2">
            <RadioGroupItem id="mode-exp" value="experiment" className="mt-1" />
            <div>
              <Label htmlFor="mode-exp" className="font-medium">
                Save and run experiment (recommended)
              </Label>
              <p className="text-xs text-muted-foreground">
                Creates the version AND launches an A/B experiment against the
                active prompt. Promotion goes through the release gate.
              </p>
            </div>
          </div>
        </RadioGroup>

        <div className="rounded-md border border-muted bg-muted/30 p-3 text-xs text-muted-foreground">
          There is no &quot;promote immediately&quot; option. All version
          changes must go through evals.
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={loading}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => onConfirm(mode)}
            disabled={loading}
          >
            {loading ? "Saving…" : "Confirm"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
