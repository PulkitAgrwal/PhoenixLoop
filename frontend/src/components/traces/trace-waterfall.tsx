"use client";

import React, { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { ToolCallRecord } from "@/lib/types";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface TraceWaterfallProps {
  toolCalls: ToolCallRecord[];
  totalLatencyMs: number;
  onSelectSpan?: (
    toolCall: ToolCallRecord | null,
    syntheticId: string | null,
  ) => void;
  selectedSpanId?: string | null;
  renderSelectedDetail?: (toolCall: ToolCallRecord) => React.ReactNode;
}

// Color coding by tool type keyword
const TOOL_TYPE_COLORS: { pattern: RegExp; bar: string; bg: string }[] = [
  {
    pattern: /lookup|get|fetch|read/i,
    bar: "bg-blue-500",
    bg: "bg-blue-50 dark:bg-blue-950/30",
  },
  {
    pattern: /search|find|query/i,
    bar: "bg-green-500",
    bg: "bg-green-50 dark:bg-green-950/30",
  },
  {
    pattern: /check|validate|verify/i,
    bar: "bg-purple-500",
    bg: "bg-purple-50 dark:bg-purple-950/30",
  },
  {
    pattern: /create|insert|add|write/i,
    bar: "bg-amber-500",
    bg: "bg-amber-50 dark:bg-amber-950/30",
  },
  {
    pattern: /draft|compose|generate/i,
    bar: "bg-teal-500",
    bg: "bg-teal-50 dark:bg-teal-950/30",
  },
  {
    pattern: /send|submit|post/i,
    bar: "bg-orange-500",
    bg: "bg-orange-50 dark:bg-orange-950/30",
  },
  {
    pattern: /delete|remove|cancel/i,
    bar: "bg-red-500",
    bg: "bg-red-50 dark:bg-red-950/30",
  },
];

const DEFAULT_COLOR = {
  bar: "bg-slate-500",
  bg: "bg-slate-50 dark:bg-slate-950/30",
};

function getToolColors(
  toolName: string
): { bar: string; bg: string } {
  for (const entry of TOOL_TYPE_COLORS) {
    if (entry.pattern.test(toolName)) {
      return { bar: entry.bar, bg: entry.bg };
    }
  }
  return DEFAULT_COLOR;
}

function formatLatency(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function getBarWidthPercent(
  latencyMs: number | null,
  totalMs: number
): number {
  if (latencyMs === null || totalMs <= 0) return 5;
  const pct = (latencyMs / totalMs) * 100;
  return Math.max(pct, 2); // minimum 2% so bars remain visible
}

export function TraceWaterfall({
  toolCalls,
  totalLatencyMs,
  onSelectSpan,
  selectedSpanId,
  renderSelectedDetail,
}: TraceWaterfallProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (toolCalls.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center rounded-lg border border-dashed">
        <p className="text-sm text-muted-foreground">No tool calls recorded</p>
      </div>
    );
  }

  const effectiveTotal =
    totalLatencyMs > 0
      ? totalLatencyMs
      : toolCalls.reduce((acc, tc) => acc + (tc.latency_ms ?? 0), 0) || 1;

  return (
    <TooltipProvider delayDuration={150}>
      <div className="space-y-1.5">
        {/* Time axis header — units match the right-hand label */}
        <div className="flex justify-between px-1 text-[10px] text-muted-foreground font-mono">
          <span>{effectiveTotal >= 1000 ? "0s" : "0ms"}</span>
          <span>{formatLatency(effectiveTotal)}</span>
        </div>

        {toolCalls.map((tc, index) => {
          const colors = getToolColors(tc.tool_name);
          const widthPct = getBarWidthPercent(tc.latency_ms, effectiveTotal);
          // span_id is null for in-memory tool call records; match by index
          // (each tc is unique within the waterfall) by encoding the index as
          // the synthetic selectedSpanId at the parent. Falls back to a
          // span_id match for tool calls that DO have real span ids.
          const syntheticId = `tc-${index}`;
          const isSelected =
            selectedSpanId === syntheticId ||
            (tc.span_id != null && tc.span_id === selectedSpanId);
          const isHovered = hoveredIndex === index;
          const isSuccess =
            tc.status === "success" || tc.status === "ok";

          return (
            <React.Fragment key={`${tc.tool_name}-${index}`}>
            <Tooltip>
              <TooltipTrigger asChild>
                <motion.div
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{
                    duration: 0.3,
                    delay: index * 0.05,
                    ease: "easeOut",
                  }}
                  className={cn(
                    "group relative flex cursor-pointer items-center gap-2 rounded px-2 py-1 transition-colors",
                    isSelected
                      ? colors.bg + " ring-2 ring-offset-1 ring-inset ring-current"
                      : isHovered
                      ? "bg-muted/60"
                      : "hover:bg-muted/40"
                  )}
                  onClick={() =>
                    onSelectSpan?.(
                      isSelected ? null : tc,
                      isSelected ? null : syntheticId,
                    )
                  }
                  onMouseEnter={() => setHoveredIndex(index)}
                  onMouseLeave={() => setHoveredIndex(null)}
                >
                  {/* Expand chevron — clear click affordance */}
                  <motion.span
                    animate={{ rotate: isSelected ? 90 : 0 }}
                    transition={{ duration: 0.15 }}
                    className="shrink-0 text-muted-foreground/60 motion-reduce:transition-none"
                  >
                    <ChevronRight className="h-3.5 w-3.5" />
                  </motion.span>

                  {/* Tool name label */}
                  <span
                    className={cn(
                      "shrink-0 font-mono text-[11px] font-medium w-44 truncate",
                      isSelected
                        ? "text-foreground"
                        : "text-muted-foreground group-hover:text-foreground"
                    )}
                  >
                    {tc.tool_name}
                  </span>

                  {/* Bar track */}
                  <div className="relative flex-1 h-5 rounded bg-muted/50">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${widthPct}%` }}
                      transition={{
                        duration: 0.4,
                        delay: index * 0.05 + 0.1,
                        ease: "easeOut",
                      }}
                      className={cn(
                        "h-full rounded",
                        colors.bar,
                        !isSuccess && "opacity-60"
                      )}
                    />
                    {/* Error indicator stripe */}
                    {!isSuccess && (
                      <div className="absolute inset-0 rounded overflow-hidden pointer-events-none">
                        <div
                          className="h-full w-full opacity-30"
                          style={{
                            backgroundImage:
                              "repeating-linear-gradient(-45deg, transparent, transparent 4px, rgba(239,68,68,0.4) 4px, rgba(239,68,68,0.4) 8px)",
                          }}
                        />
                      </div>
                    )}
                  </div>

                  {/* Latency label */}
                  <span className="shrink-0 font-mono text-[10px] text-muted-foreground w-12 text-right">
                    {formatLatency(tc.latency_ms)}
                  </span>
                </motion.div>
              </TooltipTrigger>
              <TooltipContent side="right" className="max-w-xs">
                <div className="space-y-1">
                  <p className="font-semibold text-xs font-mono">
                    {tc.tool_name}
                  </p>
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "text-xs font-medium",
                        isSuccess ? "text-green-400" : "text-red-400"
                      )}
                    >
                      {tc.status}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatLatency(tc.latency_ms)}
                    </span>
                  </div>
                  {tc.span_id && (
                    <p className="text-[10px] text-muted-foreground font-mono truncate">
                      {tc.span_id}
                    </p>
                  )}
                </div>
              </TooltipContent>
            </Tooltip>
            {/* Inline span detail — opens directly under the clicked row */}
            <AnimatePresence initial={false}>
              {isSelected && renderSelectedDetail && (
                <motion.div
                  key={`detail-${index}`}
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.18, ease: "easeOut" }}
                  className="overflow-hidden"
                >
                  <div className="pl-7 pr-1 pt-2 pb-1">
                    {renderSelectedDetail(tc)}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
            </React.Fragment>
          );
        })}
      </div>
    </TooltipProvider>
  );
}
