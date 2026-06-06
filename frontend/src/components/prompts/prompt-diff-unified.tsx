"use client";

import { useMemo } from "react";
import { diffLines } from "diff";
import { cn } from "@/lib/utils";

interface Props {
  baseline: string;
  candidate: string;
}

/**
 * Unified diff renderer. Each diff hunk shows added lines on a green
 * background, removed lines with red strikethrough, and unchanged lines
 * without highlighting. Lines wrap on long content; no horizontal scroll.
 */
export function PromptDiffUnified({ baseline, candidate }: Props) {
  const changes = useMemo(
    () => diffLines(baseline, candidate),
    [baseline, candidate],
  );

  return (
    <pre className="font-mono text-xs leading-relaxed whitespace-pre-wrap break-words">
      {changes.map((part, idx) => {
        const lines = part.value.split("\n");
        // diffLines includes the trailing newline so the last element is "" — drop it
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
