"use client";

import React, { useState } from "react";
import { CheckCircle2, XCircle, ChevronDown, ChevronRight, Wrench } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ToolCallRecord } from "@/lib/types";

interface ToolCallCardProps {
  toolCall: ToolCallRecord;
}

function formatLatency(ms: number | null): string {
  if (ms === null) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function getSummary(toolCall: ToolCallRecord): string {
  const inputKeys = Object.keys(toolCall.input ?? {});
  if (inputKeys.length === 0) return "No input params";
  const firstKey = inputKeys[0];
  const firstVal = toolCall.input[firstKey];
  const valStr =
    typeof firstVal === "string"
      ? firstVal.slice(0, 60)
      : JSON.stringify(firstVal).slice(0, 60);
  return `${firstKey}: ${valStr}${valStr.length >= 60 ? "…" : ""}`;
}

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [open, setOpen] = useState(false);
  const isSuccess = toolCall.status === "success" || toolCall.status === "ok";

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div
        className={cn(
          "rounded-lg border bg-card text-card-foreground shadow-sm overflow-hidden",
          "border-l-4",
          isSuccess ? "border-l-green-500" : "border-l-red-500"
        )}
      >
        {/* Header / Trigger */}
        <CollapsibleTrigger asChild>
          <button className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-muted/50 transition-colors">
            {/* Status icon */}
            {isSuccess ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-green-500" />
            ) : (
              <XCircle className="h-4 w-4 shrink-0 text-red-500" />
            )}

            {/* Tool icon + name */}
            <Wrench className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <span className="font-mono text-xs font-semibold text-foreground">
              {toolCall.tool_name}
            </span>

            {/* Latency badge */}
            {toolCall.latency_ms !== null && (
              <Badge
                variant="outline"
                className="ml-1 text-xs text-muted-foreground"
              >
                {formatLatency(toolCall.latency_ms)}
              </Badge>
            )}

            {/* Collapsed summary */}
            {!open && (
              <span className="ml-2 truncate text-xs text-muted-foreground">
                {getSummary(toolCall)}
              </span>
            )}

            {/* Chevron */}
            <span className="ml-auto">
              {open ? (
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
              )}
            </span>
          </button>
        </CollapsibleTrigger>

        {/* Expanded content */}
        <CollapsibleContent>
          <div className="border-t px-4 py-3 space-y-3">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Input
              </p>
              <pre className="overflow-x-auto rounded-md bg-muted px-3 py-2 text-xs leading-relaxed">
                <code>{JSON.stringify(toolCall.input, null, 2)}</code>
              </pre>
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Output
              </p>
              <pre
                className={cn(
                  "overflow-x-auto rounded-md px-3 py-2 text-xs leading-relaxed",
                  isSuccess ? "bg-green-50 dark:bg-green-950/30" : "bg-red-50 dark:bg-red-950/30"
                )}
              >
                <code>{JSON.stringify(toolCall.output, null, 2)}</code>
              </pre>
            </div>
            {toolCall.span_id && (
              <p className="text-xs text-muted-foreground">
                Span:{" "}
                <span className="font-mono">{toolCall.span_id}</span>
              </p>
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
