"use client";

import React from "react";
import { motion } from "framer-motion";
import { GitCompare } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

interface PromptDiffProps {
  proposal: Record<string, unknown> | null;
}

function splitLines(text: string): string[] {
  return text.split("\n");
}

function DiffPanel({
  title,
  lines,
  variant,
}: {
  title: string;
  lines: string[];
  variant: "removed" | "added";
}) {
  const lineNumberColor =
    variant === "removed" ? "text-red-400/60" : "text-green-400/60";
  const lineColor =
    variant === "removed" ? "text-red-300" : "text-green-300";
  const bgStripe =
    variant === "removed"
      ? "bg-red-950/40 border-l-2 border-red-700"
      : "bg-green-950/40 border-l-2 border-green-700";
  const headerColor =
    variant === "removed" ? "text-red-400" : "text-green-400";

  return (
    <div className="flex-1 min-w-0">
      <div
        className={cn(
          "text-xs font-mono px-3 py-1.5 border-b border-border bg-gray-900/60",
          headerColor
        )}
      >
        {title}
      </div>
      <ScrollArea className="h-48">
        <div className="bg-gray-950 p-3 font-mono text-xs leading-5">
          {lines.map((line, idx) => (
            <div key={idx} className={cn("flex gap-2 px-1 rounded", bgStripe)}>
              <span
                className={cn(
                  "select-none shrink-0 w-8 text-right",
                  lineNumberColor
                )}
              >
                {idx + 1}
              </span>
              <span className={cn("whitespace-pre-wrap break-all", lineColor)}>
                {line || " "}
              </span>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}

export function PromptDiff({ proposal }: PromptDiffProps) {
  if (!proposal) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <GitCompare className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm font-semibold">Prompt Diff</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No proposal generated yet.
          </p>
        </CardContent>
      </Card>
    );
  }

  const originalText =
    typeof proposal["original_text"] === "string"
      ? proposal["original_text"]
      : "";
  const proposedText =
    typeof proposal["proposed_text"] === "string"
      ? proposal["proposed_text"]
      : "";
  const patchType =
    typeof proposal["patch_type"] === "string" ? proposal["patch_type"] : null;
  const rationale =
    typeof proposal["rationale"] === "string" ? proposal["rationale"] : null;

  const originalLines = splitLines(originalText);
  const proposedLines = splitLines(proposedText);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
    >
      <Card className="overflow-hidden">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <GitCompare className="h-4 w-4 text-muted-foreground" />
              <CardTitle className="text-sm font-semibold">
                Prompt Diff
              </CardTitle>
              {patchType && (
                <Badge variant="secondary" className="text-xs capitalize">
                  {patchType.replace(/_/g, " ")}
                </Badge>
              )}
            </div>
          </div>
          {rationale && (
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
              {rationale}
            </p>
          )}
        </CardHeader>
        <CardContent className="pt-0 px-0 pb-0">
          {originalText || proposedText ? (
            <div className="flex border-t border-border divide-x divide-border rounded-b-lg overflow-hidden">
              <DiffPanel
                title="Original"
                lines={originalLines}
                variant="removed"
              />
              <DiffPanel
                title="Proposed"
                lines={proposedLines}
                variant="added"
              />
            </div>
          ) : (
            <div className="px-4 pb-4">
              <p className="text-sm text-muted-foreground">
                Proposal data is incomplete — missing original or proposed text.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
