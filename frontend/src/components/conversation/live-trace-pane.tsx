"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Activity, CheckCircle2, AlertTriangle } from "lucide-react";

import { PhoenixDeepLink } from "@/components/shared/phoenix-deep-link";
import { StatusDot } from "@/components/ui/status-dot";
import { Eyebrow } from "@/components/ui/eyebrow";
import { CodeInline } from "@/components/ui/code-inline";
import { cn } from "@/lib/utils";
import type { AgentRun, ToolCallRecord } from "@/lib/types";

type LiveTracePaneProps = {
  agentRun: AgentRun | null;
  isRunning: boolean;
};

function statusIcon(status: string) {
  if (status === "success" || status === "ok") {
    return <CheckCircle2 className="h-3.5 w-3.5 text-brand" aria-hidden />;
  }
  if (status === "error" || status === "failed") {
    return <AlertTriangle className="h-3.5 w-3.5 text-fail" aria-hidden />;
  }
  return <Activity className="h-3.5 w-3.5 text-warn" aria-hidden />;
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

function ToolSpanRow({
  toolCall,
  traceId,
  index,
}: {
  toolCall: ToolCallRecord;
  traceId: string | null | undefined;
  index: number;
}) {
  const mcp = isMcpName(toolCall.tool_name);
  return (
    <motion.li
      initial={{ opacity: 0, x: 6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.18, delay: index * 0.04 }}
      className={cn(
        "rounded-sm border bg-canvas px-3 py-2.5 font-mono text-code transition-colors",
        mcp ? "border-l-2 border-l-brand border-y-hairline border-r-hairline" : "border-hairline"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {statusIcon(toolCall.status)}
          <span
            className={cn(
              "truncate",
              mcp ? "text-brand-soft" : "text-canvas-text-soft"
            )}
          >
            {toolCall.tool_name}
          </span>
        </div>
        <PhoenixDeepLink
          spanId={toolCall.span_id ?? undefined}
          traceId={traceId ?? undefined}
        />
      </div>
      <div className="mt-1 flex items-center gap-3 text-[11px] text-mute">
        <span className="uppercase tracking-eyebrow">{toolCall.status}</span>
        <span className="num-mono">
          {toolCall.latency_ms != null ? `${toolCall.latency_ms}ms` : "—"}
        </span>
      </div>
    </motion.li>
  );
}

export function LiveTracePane({ agentRun, isRunning }: LiveTracePaneProps) {
  const toolCalls = agentRun?.tool_calls_json ?? [];
  const traceId = agentRun?.trace_id ?? null;
  const mcpCount = toolCalls.filter((t) => isMcpName(t.tool_name)).length;

  return (
    <aside
      aria-label="Live trace"
      className="flex h-full flex-col rounded-md border border-hairline bg-canvas"
    >
      <div className="flex items-center justify-between border-b border-hairline px-4 py-3">
        <div className="flex flex-col gap-0.5">
          <Eyebrow tone="mute">Live trace</Eyebrow>
          <p className="text-body-sm text-body">
            {isRunning ? "Streaming spans as the agent runs." : "Tool spans for the last run."}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {traceId ? (
            <PhoenixDeepLink traceId={traceId} label="View in Phoenix" />
          ) : null}
          {isRunning ? (
            <span className="inline-flex items-center gap-1.5 text-caption uppercase tracking-eyebrow text-brand-soft">
              <StatusDot tone="brand" size="xs" pulse />
              live
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-caption uppercase tracking-eyebrow text-mute">
              <StatusDot tone="mute" size="xs" />
              idle
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-4 border-b border-hairline px-4 py-2 text-caption">
        <span className="text-mute uppercase tracking-eyebrow">Spans</span>
        <span className="num-mono text-ink">{toolCalls.length}</span>
        <span className="text-mute uppercase tracking-eyebrow ml-2">MCP</span>
        <span className="num-mono text-brand-soft">{mcpCount}</span>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        {toolCalls.length === 0 ? (
          <p className="px-1 py-2 text-body-sm text-mute">
            {isRunning ? (
              "Capturing spans…"
            ) : (
              <>
                Run the agent and tool calls appear here.{" "}
                <CodeInline>phoenix-mcp:*</CodeInline> spans get a brand-green border.
              </>
            )}
          </p>
        ) : (
          <AnimatePresence initial={false}>
            <ol className="flex flex-col gap-2">
              {toolCalls.map((tc, i) => (
                <ToolSpanRow
                  key={tc.span_id ?? `${i}-${tc.tool_name}`}
                  toolCall={tc}
                  traceId={traceId}
                  index={i}
                />
              ))}
            </ol>
          </AnimatePresence>
        )}
      </div>

      {agentRun?.trace_id && (
        <div className="border-t border-hairline px-4 py-3">
          <PhoenixDeepLink traceId={agentRun.trace_id} label="Open full trace in Phoenix" />
        </div>
      )}
    </aside>
  );
}
