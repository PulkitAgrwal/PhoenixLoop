"use client";

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { diffLines } from "diff";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PromptDiffView } from "@/components/prompts/prompt-diff-view";

interface Props {
  baseline: string | null;
  candidate: string | null;
  baselineVersion: string;
  candidateVersion: string;
}

export function PromptChangesSection({
  baseline,
  candidate,
  baselineVersion,
  candidateVersion,
}: Props) {
  const [open, setOpen] = useState(false);

  const counts = useMemo(() => {
    if (!baseline || !candidate) return { added: 0, removed: 0 };
    const parts = diffLines(baseline, candidate);
    let added = 0;
    let removed = 0;
    for (const p of parts) {
      const lines = p.value.split("\n");
      if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
      if (p.added) added += lines.length;
      if (p.removed) removed += lines.length;
    }
    return { added, removed };
  }, [baseline, candidate]);

  if (!baseline || !candidate) {
    return (
      <Card>
        <CardHeader className="py-3">
          <p className="text-sm text-muted-foreground">
            Prompt diff not available for this experiment (created before prompt
            versioning was wired up).
          </p>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="prompt-changes-content"
        className="w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-muted/40 transition-colors rounded-t-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <motion.span
          animate={{ rotate: open ? 90 : 0 }}
          transition={{ duration: 0.2 }}
          className="text-muted-foreground motion-reduce:transition-none"
        >
          <ChevronRight className="h-4 w-4" />
        </motion.span>
        <span className="font-semibold text-sm flex-1">Prompt Changes</span>
        <span className="text-xs font-mono tabular-nums">
          <span className="text-brand-soft">+{counts.added}</span>
          {" / "}
          <span className="text-fail">-{counts.removed}</span>
        </span>
        <Badge variant="outline" className="text-xs font-mono">
          {baselineVersion} → {candidateVersion}
        </Badge>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id="prompt-changes-content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden motion-reduce:transition-none"
          >
            <CardContent className="pt-3">
              <PromptDiffView baseline={baseline} candidate={candidate} />
            </CardContent>
          </motion.div>
        )}
      </AnimatePresence>
    </Card>
  );
}
