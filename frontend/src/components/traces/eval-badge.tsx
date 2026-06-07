"use client";

import React from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { EvalResult } from "@/lib/types";

interface EvalBadgeProps {
  evalResult: EvalResult;
  compact?: boolean;
}

function isPass(evalResult: EvalResult): boolean {
  if (evalResult.outcome === "pass") return true;
  if (evalResult.outcome === "fail") return false;
  if (evalResult.score !== null) return evalResult.score >= 0.7;
  return false;
}

function getAbbreviation(name: string): string {
  // Convert snake_case to abbreviation: "response_relevance_check" -> "RRC"
  return name
    .split("_")
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("")
    .slice(0, 4);
}

export function EvalBadge({ evalResult, compact = false }: EvalBadgeProps) {
  const pass = isPass(evalResult);
  const abbrev = getAbbreviation(evalResult.evaluator_name);

  const tooltipContent = (
    <div className="space-y-1 max-w-xs">
      <p className="font-semibold text-xs">{evalResult.evaluator_name}</p>
      <div className="flex items-center gap-1.5">
        <span
          className={cn(
            "text-xs font-medium",
            pass ? "text-brand-soft" : "text-fail"
          )}
        >
          {pass ? "PASS" : "FAIL"}
        </span>
        {evalResult.score !== null && (
          <span className="text-xs text-muted-foreground">
            score: {evalResult.score.toFixed(2)}
          </span>
        )}
      </div>
      {evalResult.explanation && (
        <p className="text-xs text-muted-foreground leading-snug">
          {evalResult.explanation.slice(0, 120)}
          {evalResult.explanation.length > 120 ? "…" : ""}
        </p>
      )}
    </div>
  );

  if (compact) {
    return (
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              className={cn(
                "inline-block h-2.5 w-2.5 rounded-pill cursor-default",
                pass ? "bg-brand" : "bg-fail"
              )}
              aria-label={`${evalResult.evaluator_name}: ${pass ? "pass" : "fail"}`}
            />
          </TooltipTrigger>
          <TooltipContent side="top">{tooltipContent}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant="outline"
            className={cn(
              "inline-flex items-center gap-1 cursor-default select-none font-mono text-[11px] px-1.5 py-0.5",
              pass
                ? "border-brand/40 bg-brand/[0.06] text-brand-soft"
                : "border-fail/40 bg-fail/[0.08] text-fail"
            )}
          >
            {pass ? (
              <CheckCircle2 className="h-3 w-3 shrink-0" />
            ) : (
              <XCircle className="h-3 w-3 shrink-0" />
            )}
            {abbrev}
          </Badge>
        </TooltipTrigger>
        <TooltipContent side="top">{tooltipContent}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
