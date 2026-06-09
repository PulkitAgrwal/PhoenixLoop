"use client";

import * as React from "react";

import { Eyebrow } from "@/components/ui/eyebrow";
import { CodeInline } from "@/components/ui/code-inline";
import { cn } from "@/lib/utils";

// ─── Component ──────────────────────────────────────────────────────────────

export interface EvidenceListProps {
  evidence: string[] | null | undefined;
  /** Optional caption beside the eyebrow — e.g. the evaluator name. */
  caption?: string | null;
  className?: string;
}

export function EvidenceList({
  evidence,
  caption,
  className,
}: EvidenceListProps) {
  if (!evidence || evidence.length === 0) return null;

  const quotes = evidence
    .filter((q): q is string => typeof q === "string" && q.trim().length > 0)
    .slice(0, 3);

  if (quotes.length === 0) return null;

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <div className="flex items-baseline gap-2">
        <Eyebrow tone="mute">{"// evidence"}</Eyebrow>
        {caption ? (
          <span className="font-mono text-caption text-mute">{caption}</span>
        ) : null}
      </div>
      <ul className="flex flex-col gap-1">
        {quotes.map((quote, i) => (
          <li
            key={i}
            className="flex items-start gap-2 text-body-sm leading-5 text-body"
          >
            <span aria-hidden className="select-none text-mute">
              {"›"}
            </span>
            <CodeInline className="whitespace-pre-wrap break-words">
              {quote.length > 220 ? `${quote.slice(0, 220).trimEnd()}…` : quote}
            </CodeInline>
          </li>
        ))}
      </ul>
    </div>
  );
}
