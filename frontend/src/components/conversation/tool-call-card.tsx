"use client";

import * as React from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Loader2,
  Wrench,
  XCircle,
} from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { ToolCallRecord } from "@/lib/types";

interface ToolCallCardProps {
  toolCall: ToolCallRecord;
}

function formatLatency(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function getSummary(toolCall: ToolCallRecord): string {
  const inputKeys = Object.keys(toolCall.input ?? {});
  if (inputKeys.length === 0) return "no input";
  const firstKey = inputKeys[0];
  const firstVal = toolCall.input[firstKey];
  const valStr =
    typeof firstVal === "string"
      ? firstVal.slice(0, 60)
      : JSON.stringify(firstVal).slice(0, 60);
  return `${firstKey}: ${valStr}${valStr.length >= 60 ? "…" : ""}`;
}

type ToolCallVisualState = "success" | "pending" | "failed";

function resolveState(status: string): ToolCallVisualState {
  if (status === "success" || status === "ok") return "success";
  if (status === "pending" || status === "running" || status === "in_progress") {
    return "pending";
  }
  return "failed";
}

function isMcpName(name: string) {
  const lower = name.toLowerCase();
  return (
    lower.startsWith("phoenix-mcp") ||
    lower.includes("get-spans") ||
    lower.includes("get-span-annotations") ||
    lower.includes("get-dataset")
  );
}

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [open, setOpen] = React.useState(false);
  const state = resolveState(toolCall.status);
  const isPending = state === "pending";
  const mcp = isMcpName(toolCall.tool_name);

  const borderL =
    state === "success"
      ? "border-l-brand"
      : state === "pending"
        ? "border-l-warn"
        : "border-l-fail";

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div
        className={cn(
          "rounded-md border bg-canvas overflow-hidden border-l-[3px]",
          borderL,
          "border-y-hairline border-r-hairline"
        )}
      >
        <CollapsibleTrigger asChild>
          <button
            className="flex w-full min-w-0 items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-canvas-soft focus-visible:bg-canvas-soft"
            aria-expanded={open}
            aria-label={`${open ? "Collapse" : "Expand"} tool call ${toolCall.tool_name}`}
          >
            {state === "success" && (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-brand" aria-hidden />
            )}
            {state === "pending" && (
              <Loader2 className="h-4 w-4 shrink-0 text-warn animate-spin" aria-hidden />
            )}
            {state === "failed" && (
              <XCircle className="h-4 w-4 shrink-0 text-fail" aria-hidden />
            )}

            <Wrench className="h-3.5 w-3.5 shrink-0 text-mute" aria-hidden />
            <span
              className={cn(
                "font-mono text-code font-medium",
                mcp ? "text-brand-soft" : "text-canvas-text-soft"
              )}
            >
              {toolCall.tool_name}
            </span>

            {toolCall.latency_ms !== null && (
              <span className="num-mono text-caption text-mute">
                {formatLatency(toolCall.latency_ms)}
              </span>
            )}

            {!open && (
              <span
                className="ml-2 min-w-0 flex-1 truncate font-mono text-caption text-mute"
                title={getSummary(toolCall)}
              >
                {getSummary(toolCall)}
              </span>
            )}

            <span className="ml-auto shrink-0">
              {open ? (
                <ChevronDown className="h-3.5 w-3.5 text-mute" aria-hidden />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-mute" aria-hidden />
              )}
            </span>
          </button>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <div className="border-t border-hairline px-4 py-3 space-y-3">
            <div>
              <p className="mb-1 text-eyebrow-mono uppercase text-mute">Input</p>
              <pre className="overflow-x-auto rounded-sm bg-canvas-soft px-3 py-2 font-mono text-code text-canvas-text-soft">
                <code>{JSON.stringify(toolCall.input, null, 2)}</code>
              </pre>
            </div>
            <div>
              <p className="mb-1 text-eyebrow-mono uppercase text-mute">Output</p>
              <pre className="overflow-x-auto rounded-sm bg-canvas-soft px-3 py-2 font-mono text-code text-canvas-text-soft">
                <code>
                  {isPending
                    ? "Waiting for tool to return…"
                    : JSON.stringify(toolCall.output, null, 2)}
                </code>
              </pre>
            </div>
            {toolCall.span_id && (
              <p className="text-caption text-mute">
                Span: <span className="font-mono text-canvas-text-soft">{toolCall.span_id}</span>
              </p>
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
