"use client";

import * as React from "react";

import { StatusDot, type StatusTone } from "@/components/ui/status-dot";
import { cn } from "@/lib/utils";

// ─── Types ──────────────────────────────────────────────────────────────────

export type RuleStatus = "pass" | "fail" | "skipped";

export interface RuleRowProps {
  name: string;
  status: RuleStatus | string;
  required: string;
  actual: string;
  className?: string;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function humanizeName(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusTone(status: string): StatusTone {
  if (status === "pass") return "brand";
  if (status === "fail") return "fail";
  return "mute";
}

function statusLabel(status: string): string {
  if (status === "pass") return "pass";
  if (status === "fail") return "fail";
  if (status === "skipped") return "skipped";
  return status;
}

// ─── Component ──────────────────────────────────────────────────────────────

export function RuleRow({
  name,
  status,
  required,
  actual,
  className,
}: RuleRowProps) {
  const tone = statusTone(status);
  const dimmed = status === "skipped";

  return (
    <div
      className={cn(
        "grid grid-cols-[auto_1fr_auto] items-start gap-3 rounded-md border border-hairline bg-canvas px-3 py-2.5",
        dimmed && "opacity-60",
        className
      )}
    >
      <div className="mt-1">
        <StatusDot tone={tone} size="sm" />
      </div>
      <div className="min-w-0 flex flex-col gap-1">
        <span
          className={cn(
            "text-body-sm-strong",
            tone === "brand" && "text-ink-strong",
            tone === "fail" && "text-ink-strong",
            tone === "mute" && "text-ink"
          )}
        >
          {humanizeName(name)}
        </span>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 font-mono text-code text-mute">
          <span>
            <span className="text-mute">required </span>
            <span className="text-canvas-text-soft">{required || "—"}</span>
          </span>
          <span aria-hidden className="text-mute opacity-60">
            ·
          </span>
          <span>
            <span className="text-mute">actual </span>
            <span
              className={cn(
                tone === "brand" && "text-brand-soft",
                tone === "fail" && "text-fail",
                tone === "mute" && "text-canvas-text-soft"
              )}
            >
              {actual || "—"}
            </span>
          </span>
        </div>
      </div>
      <span
        className={cn(
          "text-eyebrow-mono uppercase tracking-eyebrow",
          tone === "brand" && "text-brand-soft",
          tone === "fail" && "text-fail",
          tone === "mute" && "text-mute"
        )}
      >
        {statusLabel(status)}
      </span>
    </div>
  );
}
