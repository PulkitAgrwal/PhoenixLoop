"use client";

import React from "react";
import { Clock, Wrench } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { StatusBadge } from "@/components/shared/status-badge";
import { EvalBadge } from "@/components/traces/eval-badge";
import { ToolCallRecord, EvalResult } from "@/lib/types";

interface SpanDetailProps {
  toolCall: ToolCallRecord;
  evalResults?: EvalResult[];
}

function formatLatency(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function getStatusVariant(
  status: string
): "success" | "error" | "warning" | "pending" {
  if (status === "success" || status === "ok") return "success";
  if (status === "error" || status === "failed") return "error";
  if (status === "pending") return "pending";
  return "warning";
}

export function SpanDetail({ toolCall, evalResults = [] }: SpanDetailProps) {
  const spanEvals = evalResults.filter(
    (e) => e.span_id && toolCall.span_id && e.span_id === toolCall.span_id
  );

  return (
    <Card className="w-full">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Wrench className="h-4 w-4 text-muted-foreground" />
          <span className="font-mono">{toolCall.tool_name}</span>
          <div className="ml-auto flex items-center gap-2">
            <StatusBadge
              status={getStatusVariant(toolCall.status)}
              label={toolCall.status}
            />
            <span className="flex items-center gap-1 text-sm text-muted-foreground">
              <Clock className="h-3.5 w-3.5" />
              {formatLatency(toolCall.latency_ms)}
            </span>
          </div>
        </CardTitle>
        {toolCall.span_id && (
          <p className="text-xs text-muted-foreground font-mono">
            span: {toolCall.span_id}
          </p>
        )}
      </CardHeader>

      <Separator />

      <CardContent className="pt-4 space-y-4">
        {/* Input */}
        <div>
          <p className="mb-1 text-eyebrow-mono uppercase text-mute">Input</p>
          <pre className="overflow-x-auto rounded-sm bg-canvas-soft px-3 py-2 font-mono text-code text-canvas-text-soft max-h-48">
            <code>{JSON.stringify(toolCall.input, null, 2)}</code>
          </pre>
        </div>

        <Separator />

        {/* Output */}
        <div>
          <p className="mb-1 text-eyebrow-mono uppercase text-mute">Output</p>
          <pre className="overflow-x-auto rounded-sm bg-canvas-soft px-3 py-2 font-mono text-code text-canvas-text-soft max-h-48">
            <code>{JSON.stringify(toolCall.output, null, 2)}</code>
          </pre>
        </div>

        {/* Span-level eval results */}
        {spanEvals.length > 0 && (
          <>
            <Separator />
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Span Evaluations
              </p>
              <div className="flex flex-wrap gap-1.5">
                {spanEvals.map((e) => (
                  <EvalBadge key={e.eval_result_id} evalResult={e} />
                ))}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
