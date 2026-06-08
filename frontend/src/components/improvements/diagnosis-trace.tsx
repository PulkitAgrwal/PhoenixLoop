"use client";

import * as React from "react";
import { motion } from "framer-motion";

import { Eyebrow } from "@/components/ui/eyebrow";
import { StatusDot } from "@/components/ui/status-dot";
import { CodeInline } from "@/components/ui/code-inline";
import { cn } from "@/lib/utils";

interface DiagnosisTraceProps {
  diagnosis: Record<string, unknown> | null;
}

function getStringField(diagnosis: Record<string, unknown>, key: string): string | null {
  const v = diagnosis[key];
  return typeof v === "string" && v.length > 0 ? v : null;
}

function getConfidence(diagnosis: Record<string, unknown>): string | null {
  const raw = diagnosis["confidence"];
  if (typeof raw === "number") return `${(raw * 100).toFixed(0)}%`;
  if (typeof raw === "string") return raw;
  return null;
}

export function DiagnosisTrace({ diagnosis }: DiagnosisTraceProps) {
  const hasDiagnosis = diagnosis !== null && Object.keys(diagnosis).length > 0;

  const tools = React.useMemo<string[]>(() => {
    if (!diagnosis) return [];
    const raw = diagnosis["mcp_tools_used"];
    if (!Array.isArray(raw)) return [];
    return raw.filter((t): t is string => typeof t === "string");
  }, [diagnosis]);

  const evidence = hasDiagnosis ? getStringField(diagnosis!, "evidence_summary") : null;
  const failurePattern = hasDiagnosis ? getStringField(diagnosis!, "failure_pattern") : null;
  const confidence = hasDiagnosis ? getConfidence(diagnosis!) : null;

  return (
    <section
      aria-label="Diagnosis trace"
      className="rounded-md border border-hairline bg-canvas overflow-hidden"
    >
      <header className="flex items-center justify-between border-b border-hairline bg-canvas-soft px-4 py-2.5">
        <div className="flex items-center gap-2">
          <StatusDot
            tone={hasDiagnosis ? "brand" : "mute"}
            size="xs"
            pulse={!hasDiagnosis}
          />
          <Eyebrow tone={hasDiagnosis ? "brand" : "mute"}>Diagnosis trace</Eyebrow>
        </div>
        <span className="font-mono text-caption text-mute">
          {hasDiagnosis ? `${tools.length} MCP tool${tools.length === 1 ? "" : "s"}` : "no run"}
        </span>
      </header>

      <div className="px-4 py-3">
        {!hasDiagnosis ? (
          <p className="text-body-sm text-mute">
            Run <CodeInline>Read failing spans via Phoenix MCP</CodeInline> to invoke the diagnosis sub-agent.
            The agent calls <CodeInline>phoenix-mcp:get-spans</CodeInline> and{" "}
            <CodeInline>phoenix-mcp:get-span-annotations</CodeInline>, reads its own failing
            spans, and names the recurring pattern.
          </p>
        ) : (
          <ol className="flex flex-col gap-2">
            {tools.length > 0 ? (
              tools.map((tool, i) => (
                <motion.li
                  key={`${tool}-${i}`}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.18, delay: i * 0.08 }}
                  className={cn(
                    "flex items-center justify-between gap-3 rounded-sm border border-y-hairline border-r-hairline border-l-2 border-l-brand bg-canvas-soft px-3 py-2 font-mono text-code"
                  )}
                >
                  <span className="flex items-center gap-2 truncate">
                    <span className="text-mute">{`0${i + 1}`}</span>
                    <span className="text-brand-soft">phoenix-mcp</span>
                    <span className="text-mute">·</span>
                    <span className="text-canvas-text-soft truncate">{tool}</span>
                  </span>
                  <span className="text-caption uppercase tracking-eyebrow text-mute">ok</span>
                </motion.li>
              ))
            ) : (
              <li className="rounded-sm border border-hairline bg-canvas-soft px-3 py-2 text-body-sm text-mute">
                The diagnosis returned without naming an MCP tool — likely the degraded fallback
                path (no Phoenix MCP available). The diagnosis text below is still valid.
              </li>
            )}

            {failurePattern && (
              <li className="rounded-sm border border-hairline bg-canvas-soft px-3 py-2">
                <div className="text-eyebrow-mono uppercase text-mute">Pattern</div>
                <p className="mt-0.5 text-body-sm text-ink">{failurePattern}</p>
              </li>
            )}

            {evidence && (
              <li className="rounded-sm border border-hairline bg-canvas-soft px-3 py-2">
                <div className="text-eyebrow-mono uppercase text-mute">Evidence summary</div>
                <p className="mt-0.5 text-body-sm text-ink">{evidence}</p>
              </li>
            )}

            <li className="flex items-center justify-between gap-3 border-t border-hairline pt-2 px-1 text-caption text-mute">
              <span className="uppercase tracking-eyebrow">verdict</span>
              <span className="num-mono text-brand-soft">{confidence ?? "—"} confidence</span>
            </li>
          </ol>
        )}
      </div>
    </section>
  );
}
