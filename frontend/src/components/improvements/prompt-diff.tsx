"use client";

import * as React from "react";
import { diffLines, type Change } from "diff";

import { Eyebrow } from "@/components/ui/eyebrow";
import { Tag } from "@/components/ui/tag";
import { cn } from "@/lib/utils";

interface PromptDiffProps {
  proposal: Record<string, unknown> | null;
}

interface DiffRow {
  kind: "context" | "added" | "removed";
  text: string;
}

function buildRows(original: string, proposed: string): DiffRow[] {
  if (!original && !proposed) return [];
  const parts: Change[] = diffLines(original, proposed);
  const rows: DiffRow[] = [];
  for (const part of parts) {
    const lines = part.value.replace(/\n$/, "").split("\n");
    for (const line of lines) {
      rows.push({
        kind: part.added ? "added" : part.removed ? "removed" : "context",
        text: line,
      });
    }
  }
  return rows;
}

export function PromptDiff({ proposal }: PromptDiffProps) {
  const originalText =
    proposal && typeof proposal["original_text"] === "string"
      ? proposal["original_text"]
      : "";
  const proposedText =
    proposal && typeof proposal["proposed_text"] === "string"
      ? proposal["proposed_text"]
      : "";
  const patchType =
    proposal && typeof proposal["patch_type"] === "string"
      ? proposal["patch_type"]
      : null;
  const rationale =
    proposal && typeof proposal["rationale"] === "string"
      ? proposal["rationale"]
      : null;

  const rows = React.useMemo(
    () => buildRows(originalText, proposedText),
    [originalText, proposedText]
  );
  const addedCount = rows.filter((r) => r.kind === "added").length;
  const removedCount = rows.filter((r) => r.kind === "removed").length;

  return (
    <section
      aria-label="Prompt diff"
      className="rounded-md border border-hairline bg-canvas overflow-hidden"
    >
      <header className="flex items-center justify-between border-b border-hairline bg-canvas-soft px-4 py-2.5">
        <div className="flex items-center gap-3">
          <Eyebrow tone="brand">Prompt diff</Eyebrow>
          {patchType && (
            <span className="font-mono text-caption text-mute">
              {patchType.replace(/_/g, " ")}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Tag tone="brand">+ {addedCount}</Tag>
          <Tag tone="mute">− {removedCount}</Tag>
        </div>
      </header>

      {!proposal ? (
        <p className="px-4 py-4 text-body-sm text-mute">
          No proposal yet. Click <span className="text-ink">Analyze</span> to invoke the diagnosis
          sub-agent and synthesize a one-line prompt patch.
        </p>
      ) : rows.length === 0 ? (
        <p className="px-4 py-4 text-body-sm text-mute">
          Proposal data is incomplete — missing original or proposed text.
        </p>
      ) : (
        <>
          {rationale && (
            <p className="border-b border-hairline px-4 py-3 text-body-sm text-body">
              {rationale}
            </p>
          )}
          <pre className="overflow-x-auto bg-canvas-soft px-4 py-3 font-mono text-code leading-[18px]">
            <code>
              {rows.map((r, i) => (
                <div
                  key={i}
                  className={cn(
                    "flex items-baseline gap-3 px-1 py-[1px]",
                    r.kind === "added" && "bg-brand/[0.08]",
                    r.kind === "removed" && "bg-canvas"
                  )}
                >
                  <span className="num-mono w-8 select-none text-right text-mute opacity-60">
                    {i + 1}
                  </span>
                  <span
                    aria-hidden
                    className={cn(
                      "w-3 shrink-0",
                      r.kind === "added"
                        ? "text-brand"
                        : r.kind === "removed"
                          ? "text-mute"
                          : "text-mute opacity-40"
                    )}
                  >
                    {r.kind === "added" ? "+" : r.kind === "removed" ? "−" : " "}
                  </span>
                  <span
                    className={cn(
                      "whitespace-pre-wrap break-words",
                      r.kind === "added"
                        ? "text-brand-soft"
                        : r.kind === "removed"
                          ? "text-mute line-through decoration-mute/60"
                          : "text-canvas-text-soft"
                    )}
                  >
                    {r.text || " "}
                  </span>
                </div>
              ))}
            </code>
          </pre>
        </>
      )}
    </section>
  );
}
