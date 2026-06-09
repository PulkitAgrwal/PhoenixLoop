"use client";

import * as React from "react";
import { ShieldAlert } from "lucide-react";

import { Tag, type TagTone } from "@/components/ui/tag";
import { cn } from "@/lib/utils";

// ─── Taxonomy ───────────────────────────────────────────────────────────────

export type ChangeClass =
  | "prompt_addition"
  | "tool_policy"
  | "routing"
  | "data_source"
  | "eval_definition"
  | "manual_edit"
  | "seed";

interface ClassMeta {
  label: string;
  description: string;
  tone: TagTone;
}

const META: Record<ChangeClass, ClassMeta> = {
  prompt_addition: {
    label: "Prompt addition",
    description: "Appends or tightens guidance inside the system prompt.",
    tone: "brand",
  },
  tool_policy: {
    label: "Tool policy",
    description: "Constrains which tools the agent must / must not call.",
    tone: "default",
  },
  routing: {
    label: "Routing",
    description: "Changes how the agent routes a category of input.",
    tone: "default",
  },
  data_source: {
    label: "Data source",
    description: "Swaps or filters the retrieval source used by the agent.",
    tone: "default",
  },
  eval_definition: {
    label: "Eval definition",
    description: "Alters the rubric or threshold an evaluator uses.",
    tone: "warn",
  },
  manual_edit: {
    label: "Manual edit",
    description: "Hand-edited prompt — no diagnosis pipeline involved.",
    tone: "mute",
  },
  seed: {
    label: "Seed",
    description: "Initial seed prompt — no diagnosis pipeline involved.",
    tone: "mute",
  },
};

const HIGH_RISK_COPY =
  "High-risk: alters quality standards — extra scrutiny applies.";

// ─── Component ──────────────────────────────────────────────────────────────

export interface ChangeClassBadgeProps {
  changeClass: ChangeClass | string | null | undefined;
  label?: string | null;
  isHighRisk?: boolean;
  className?: string;
}

function isKnownClass(value: string): value is ChangeClass {
  return value in META;
}

export function ChangeClassBadge({
  changeClass,
  label,
  isHighRisk,
  className,
}: ChangeClassBadgeProps) {
  if (!changeClass) return null;

  const known = isKnownClass(changeClass) ? META[changeClass] : null;
  const displayLabel =
    label && label.length > 0 ? label : known?.label ?? changeClass;
  const tone: TagTone = known?.tone ?? "default";
  const description = known?.description ?? "";
  // Eval-definition class implicitly carries the high-risk flag too.
  const showHighRisk = Boolean(isHighRisk) || changeClass === "eval_definition";

  return (
    <div
      className={cn(
        "flex flex-col gap-2",
        showHighRisk &&
          "rounded-md border-l-2 border-l-brand bg-canvas-soft px-3 py-2.5",
        className
      )}
    >
      <div className="flex items-center gap-2">
        <span className="text-eyebrow-mono uppercase tracking-eyebrow text-mute">
          change class
        </span>
        <Tag tone={tone} title={description}>
          {displayLabel}
        </Tag>
      </div>
      {showHighRisk && (
        <Tag
          tone="warn"
          className="self-start gap-2"
          aria-label="High-risk change"
        >
          <ShieldAlert className="h-3 w-3 shrink-0" aria-hidden />
          <span>{HIGH_RISK_COPY}</span>
        </Tag>
      )}
    </div>
  );
}
