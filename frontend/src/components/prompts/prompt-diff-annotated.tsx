"use client";

import { useMemo } from "react";
import { diffLines } from "diff";
import { cn } from "@/lib/utils";

interface Props {
  baseline: string;
  candidate: string;
}

/**
 * Annotated full-text renderer. Renders both baseline-only and candidate-only
 * lines with diff annotations. Visually similar to the unified diff today —
 * spec 0b reserves these as two components so spec B can later collapse the
 * unified view's unchanged runs without affecting this one.
 */
export function PromptDiffAnnotated({ baseline, candidate }: Props) {
  const changes = useMemo(
    () => diffLines(baseline, candidate),
    [baseline, candidate],
  );

  return (
    <pre className="font-mono text-xs leading-relaxed whitespace-pre-wrap break-words">
      {changes.map((part, idx) => {
        const lines = part.value.split("\n");
        if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
        return (
          <span key={idx}>
            {lines.map((line, i) => (
              <span
                key={i}
                className={cn(
                  "block px-2",
                  part.added &&
                    "bg-green-50 text-green-900 dark:bg-green-950/40 dark:text-green-100",
                  part.removed &&
                    "bg-red-50 text-red-900 line-through dark:bg-red-950/40 dark:text-red-100",
                )}
              >
                <span className="select-none text-muted-foreground mr-2">
                  {part.added ? "+" : part.removed ? "-" : " "}
                </span>
                {line || "​"}
              </span>
            ))}
          </span>
        );
      })}
    </pre>
  );
}
