"use client";

import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, ExternalLink, Play, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { StatusBadge } from "@/components/shared/status-badge";
import { MessageBubble } from "@/components/conversation/message-bubble";
import { ToolCallCard } from "@/components/conversation/tool-call-card";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { StreamEvent } from "@/lib/api";
import {
  SupportTicket,
  AgentRun,
  EvalResult,
  ToolCallRecord,
} from "@/lib/types";

interface ChatInterfaceProps {
  ticket: SupportTicket | null;
  onRunStateChange?: (running: boolean) => void;
  onLastRunChange?: (run: AgentRun | null) => void;
}

interface ChatMessage {
  id: string;
  role: "user" | "agent";
  content: string;
  timestamp: string;
  toolCalls?: ToolCallRecord[];
  evals?: EvalResult[];
  traceId?: string | null;
  phoenixSessionId?: string | null;
}

function TypingIndicator({ phase }: { phase: "thinking" | "evals" }) {
  const label = phase === "thinking" ? "agent thinking" : "running evals";
  const dotClass = phase === "thinking" ? "bg-brand" : "bg-mute";
  return (
    <motion.div
      key={phase}
      initial={{ opacity: 0, x: -16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -16 }}
      transition={{ duration: 0.2 }}
      className="flex items-center gap-2 pl-11"
    >
      <div className="flex items-center gap-2 rounded-md border border-hairline bg-canvas-soft px-4 py-3">
        <span className="font-mono text-code text-mute">{label}</span>
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className={cn("block h-1.5 w-1.5 rounded-pill", dotClass)}
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{
              repeat: Infinity,
              duration: 1.2,
              delay: i * 0.18,
              ease: "easeInOut",
            }}
            aria-hidden
          />
        ))}
      </div>
    </motion.div>
  );
}

function EvalBadgeRow({ evals }: { evals: EvalResult[] }) {
  if (evals.length === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: 0.1 }}
      className="flex flex-wrap items-center gap-2 pl-11"
    >
      <span className="text-xs text-muted-foreground font-medium">Evals:</span>
      {evals.map((ev) => {
        const passed =
          ev.outcome === "pass" ||
          ev.outcome === "passed" ||
          (ev.score !== null && ev.score >= 0.5);
        return (
          <StatusBadge
            key={ev.eval_result_id}
            status={passed ? "success" : "error"}
            label={ev.evaluator_name.replace(/_/g, " ")}
          />
        );
      })}
    </motion.div>
  );
}

function extractAgentText(run: AgentRun): string {
  const resp = run.response_json;
  if (!resp) return "(No response)";
  if (typeof resp["text"] === "string") return resp["text"];
  if (typeof resp["content"] === "string") return resp["content"];
  if (typeof resp["message"] === "string") return resp["message"];
  if (typeof resp["answer"] === "string") return resp["answer"];
  if (typeof resp["response"] === "string") return resp["response"];
  return JSON.stringify(resp, null, 2);
}

// The agent streams a JSON document character-by-character (matches the
// AgentResponseContract schema). Pull the answer field out of the partial
// stream so the bubble shows clean prose instead of a raw JSON dump.
function extractStreamedAnswer(text: string): string {
  if (!text) return "";
  const trimmed = text.trimStart();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return text;
  for (const field of ["answer", "text", "content", "message", "response"]) {
    const re = new RegExp(`"${field}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)`);
    const match = text.match(re);
    if (match) {
      try {
        return JSON.parse(`"${match[1]}"`);
      } catch {
        return match[1]
          .replace(/\\n/g, "\n")
          .replace(/\\t/g, "\t")
          .replace(/\\"/g, '"')
          .replace(/\\\\/g, "\\");
      }
    }
  }
  return "";
}

export function ChatInterface({
  ticket,
  onRunStateChange,
  onLastRunChange,
}: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<AgentRun | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    onRunStateChange?.(isRunning);
  }, [isRunning, onRunStateChange]);

  useEffect(() => {
    onLastRunChange?.(lastRun);
  }, [lastRun, onLastRunChange]);

  // Reset conversation when ticket changes
  useEffect(() => {
    setMessages([]);
    setError(null);
    setIsRunning(false);
    setLastRun(null);

    if (ticket) {
      setMessages([
        {
          id: `user-${ticket.ticket_id}`,
          role: "user",
          content: ticket.body,
          timestamp: ticket.created_at,
        },
      ]);
    }
  }, [ticket?.ticket_id]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (scrollRef.current) {
      const viewport = scrollRef.current.querySelector(
        "[data-radix-scroll-area-viewport]"
      ) as HTMLElement | null;
      if (viewport) {
        viewport.scrollTop = viewport.scrollHeight;
      }
    }
  }, [messages, isRunning]);

  const handleRun = async () => {
    if (!ticket || isRunning) return;
    setError(null);
    setIsRunning(true);

    // Build an in-flight agent message that we mutate as events arrive.
    // `currentId` starts as a synthetic placeholder and is swapped to the real
    // agent_run_id when the `agent_done` event lands, so subsequent eval
    // updates still find the message.
    let currentId = `agent-inflight-${Date.now()}`;
    const inflightCreatedAt = new Date().toISOString();
    const toolsByIndex = new Map<number, ToolCallRecord>();
    const evalsAccum: EvalResult[] = [];
    let liveText = "";

    setMessages((prev) => [
      ...prev,
      {
        id: currentId,
        role: "agent",
        content: "",
        timestamp: inflightCreatedAt,
        toolCalls: [],
        evals: [],
        traceId: null,
        phoenixSessionId: null,
      },
    ]);

    const renderInflight = () => {
      const orderedTools = Array.from(toolsByIndex.entries())
        .sort(([a], [b]) => a - b)
        .map(([, tc]) => tc);
      const targetId = currentId;
      const displayText = extractStreamedAnswer(liveText) || liveText;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === targetId
            ? {
                ...m,
                content: displayText,
                toolCalls: orderedTools,
                evals: [...evalsAccum],
              }
            : m,
        ),
      );
      // Surface live tool calls to the LiveTracePane via lastRun so the
      // right-hand trace pane updates in step with the chat panel.
      setLastRun((prev) => {
        const base: AgentRun =
          prev ??
          ({
            agent_run_id: "inflight",
            conversation_session_id: "",
            ticket_id: ticket?.ticket_id ?? "",
            agent_name: "helios_support_agent",
            agent_version: "1.0.0",
            prompt_version: "production",
            trace_id: null,
            root_span_id: null,
            phoenix_session_id: null,
            input_hash: null,
            response_json: {},
            tool_calls_json: [],
            status: "running",
            latency_ms: null,
            token_count_input: null,
            token_count_output: null,
            created_at: inflightCreatedAt,
          } as AgentRun);
        return { ...base, tool_calls_json: orderedTools };
      });
    };

    const handleEvent = (event: StreamEvent) => {
      switch (event.type) {
        case "agent_start":
          break;
        case "tool_call_started": {
          toolsByIndex.set(event.index, {
            tool_name: event.tool_name,
            input: event.input,
            output: {},
            status: "pending",
            latency_ms: null,
            span_id: null,
          } as ToolCallRecord);
          renderInflight();
          break;
        }
        case "tool_call_completed": {
          const existing = toolsByIndex.get(event.index);
          toolsByIndex.set(event.index, {
            ...(existing ?? {
              tool_name: event.tool_name,
              input: {},
              span_id: null,
            }),
            output: event.output,
            status: event.status,
            latency_ms: event.latency_ms,
          } as ToolCallRecord);
          renderInflight();
          break;
        }
        case "text_chunk":
          liveText += event.text;
          renderInflight();
          break;
        case "agent_done": {
          const run = event.agent_run as unknown as AgentRun;
          setLastRun(run);
          const previousId = currentId;
          const newId = `agent-${run.agent_run_id}`;
          currentId = newId;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === previousId
                ? {
                    ...m,
                    id: newId,
                    content: extractAgentText(run),
                    timestamp: run.created_at,
                    toolCalls: run.tool_calls_json ?? Array.from(toolsByIndex.values()),
                    traceId: run.trace_id,
                    phoenixSessionId: run.phoenix_session_id,
                  }
                : m,
            ),
          );
          break;
        }
        case "eval_result":
          evalsAccum.push(event.result as unknown as EvalResult);
          renderInflight();
          break;
        case "done":
          break;
        case "error":
          setError(event.error);
          break;
      }
    };

    try {
      await api.tickets.runStream(ticket.ticket_id, handleEvent);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unexpected error");
    } finally {
      setIsRunning(false);
    }
  };

  const handleReset = () => {
    setMessages([]);
    setError(null);
    setLastRun(null);
    if (ticket) {
      setMessages([
        {
          id: `user-${ticket.ticket_id}-reset-${Date.now()}`,
          role: "user",
          content: ticket.body,
          timestamp: ticket.created_at,
        },
      ]);
    }
  };

  const hasAgentResponse = messages.some((m) => m.role === "agent");
  const lastAgentMsg = [...messages].reverse().find((m) => m.role === "agent");
  const hasStreamedText =
    (lastAgentMsg?.content?.trim().length ?? 0) > 0;
  const indicatorPhase: "thinking" | "evals" = hasStreamedText
    ? "evals"
    : "thinking";
  const phoenixBaseUrl =
    process.env.NEXT_PUBLIC_PHOENIX_URL ?? "http://localhost:6006";

  if (!ticket) {
    return (
      <div className="flex h-full min-h-[480px] items-center justify-center rounded-md border border-hairline bg-canvas">
        <div className="flex max-w-[42ch] flex-col items-center gap-3 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-sm border border-hairline bg-canvas-soft text-mute">
            <Activity className="h-5 w-5" aria-hidden />
          </div>
          <p className="text-body-md-strong text-ink-strong">No ticket selected.</p>
          <p className="text-body-sm text-body">
            Pick a scenario above to load a customer message and run the agent against it.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {!hasAgentResponse && !isRunning && (
            <Button
              onClick={handleRun}
              disabled={isRunning}
              size="sm"
              className="gap-2"
            >
              <Play className="h-3.5 w-3.5" />
              Run Agent
            </Button>
          )}
          {hasAgentResponse && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleReset}
              className="gap-2"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Reset
            </Button>
          )}
          {/* Phoenix tracing badge */}
          <AnimatePresence>
            {isRunning && (
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ duration: 0.2 }}
              >
                <StatusBadge
                  status="info"
                  label="Tracing to Phoenix..."
                  pulse
                />
              </motion.div>
            )}
          </AnimatePresence>

          {/* View Trace button after completion */}
          {hasAgentResponse && lastRun?.trace_id && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
            >
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                asChild
              >
                <a
                  href={`${phoenixBaseUrl}/traces/${lastRun.trace_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  View Trace
                </a>
              </Button>
            </motion.div>
          )}
        </div>

        {/* Ticket meta */}
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-mono">{ticket.ticket_id.slice(0, 8)}…</span>
          {lastRun?.latency_ms != null && (
            <span className="text-muted-foreground/70">
              {lastRun.latency_ms}ms
            </span>
          )}
        </div>
      </div>

      {/* Chat window */}
      <div className="rounded-md border border-hairline bg-canvas overflow-hidden">
        <ScrollArea ref={scrollRef} className="h-[520px] w-full">
          <div className="flex flex-col gap-5 p-6">
            <AnimatePresence initial={false}>
              {messages.map((msg) => (
                <React.Fragment key={msg.id}>
                  {/* Render the bubble only when we have something to say.
                      In-flight agent messages start with empty content while
                      tool calls stream in; the empty pill + avatar looked
                      broken, so we suppress it until text arrives. The tool
                      call list + typing indicator already signal activity. */}
                  {(msg.role === "user" || msg.content.trim().length > 0) && (
                    <MessageBubble
                      role={msg.role}
                      content={msg.content}
                      timestamp={msg.timestamp}
                    />
                  )}

                  {/* Tool calls (shown after agent message) */}
                  {msg.role === "agent" &&
                    msg.toolCalls &&
                    msg.toolCalls.length > 0 && (
                      <motion.div
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.25 }}
                        className="flex flex-col gap-2 pl-11"
                      >
                        <p className="text-xs font-medium text-muted-foreground">
                          Tool calls ({msg.toolCalls.length})
                        </p>
                        {msg.toolCalls.map((tc, idx) => (
                          <ToolCallCard
                            key={tc.span_id ?? `${msg.id}-tool-${idx}`}
                            toolCall={tc}
                          />
                        ))}
                      </motion.div>
                    )}

                  {/* Eval badges */}
                  {msg.role === "agent" && msg.evals && msg.evals.length > 0 && (
                    <>
                      <Separator className="mx-11" />
                      <EvalBadgeRow evals={msg.evals} />
                    </>
                  )}
                </React.Fragment>
              ))}
            </AnimatePresence>

            {/* Typing indicator */}
            <AnimatePresence mode="wait">
              {isRunning && <TypingIndicator phase={indicatorPhase} />}
            </AnimatePresence>

            {/* Error */}
            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className={cn(
                    "mx-auto rounded-md border border-fail/40 bg-fail/[0.08] px-4 py-3",
                    "text-body-sm text-fail"
                  )}
                >
                  <strong>Error: </strong>
                  {error}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}
