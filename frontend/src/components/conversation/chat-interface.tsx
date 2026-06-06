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
import {
  SupportTicket,
  AgentRun,
  EvalResult,
  ToolCallRecord,
} from "@/lib/types";

interface ChatInterfaceProps {
  ticket: SupportTicket | null;
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

function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, x: -16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -16 }}
      transition={{ duration: 0.2 }}
      className="flex items-center gap-2 pl-11"
    >
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm border border-border bg-muted px-4 py-3 shadow-sm">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="block h-2 w-2 rounded-full bg-muted-foreground/60"
            animate={{ y: [0, -5, 0] }}
            transition={{
              repeat: Infinity,
              duration: 0.8,
              delay: i * 0.15,
              ease: "easeInOut",
            }}
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

export function ChatInterface({ ticket }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<AgentRun | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

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

    try {
      const res = await api.tickets.run(ticket.ticket_id);
      if (!res.ok || !res.data) {
        setError(res.error ?? "Agent run failed");
        return;
      }

      // POST /tickets/{id}/run wraps the result as
      // { agent_run, eval_results, triggers_created } — unwrap it.
      const payload = res.data as {
        agent_run: AgentRun;
        eval_results: EvalResult[];
        triggers_created: number;
      };
      const run = payload.agent_run;
      const evals = payload.eval_results ?? [];
      setLastRun(run);

      const agentText = extractAgentText(run);

      setMessages((prev) => [
        ...prev,
        {
          id: `agent-${run.agent_run_id}`,
          role: "agent",
          content: agentText,
          timestamp: run.created_at,
          toolCalls: run.tool_calls_json ?? [],
          evals,
          traceId: run.trace_id,
          phoenixSessionId: run.phoenix_session_id,
        },
      ]);
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
  const phoenixBaseUrl =
    process.env.NEXT_PUBLIC_PHOENIX_URL ?? "http://localhost:6006";

  if (!ticket) {
    return (
      <div className="flex h-full min-h-[400px] items-center justify-center text-center">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
            <Activity className="h-6 w-6" />
          </div>
          <p className="text-sm font-medium">Select a ticket scenario above</p>
          <p className="text-xs">
            Choose a demo support ticket to run the agent and observe the conversation.
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
      <div className="rounded-xl border bg-background shadow-sm overflow-hidden">
        <ScrollArea ref={scrollRef} className="h-[520px] w-full">
          <div className="flex flex-col gap-5 p-6">
            <AnimatePresence initial={false}>
              {messages.map((msg) => (
                <React.Fragment key={msg.id}>
                  <MessageBubble
                    role={msg.role}
                    content={msg.content}
                    timestamp={msg.timestamp}
                  />

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
            <AnimatePresence>
              {isRunning && <TypingIndicator />}
            </AnimatePresence>

            {/* Error */}
            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className={cn(
                    "mx-auto rounded-lg border border-red-200 bg-red-50 px-4 py-3",
                    "text-sm text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-400"
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
