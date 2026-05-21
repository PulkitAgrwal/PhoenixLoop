"use client";

import React from "react";
import { motion } from "framer-motion";
import { TestTube, Target, AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

interface RegressionListProps {
  regressions: Record<string, unknown>[];
}

interface RegressionItem {
  inputSummary: string;
  expectedBehavior: string;
  failureModeTargeted: string;
}

function extractRegressionItem(
  item: Record<string, unknown>
): RegressionItem {
  // input_ticket can be a string or an object — derive a summary
  const rawTicket = item["input_ticket"];
  let inputSummary = "(No input)";
  if (typeof rawTicket === "string") {
    inputSummary = rawTicket.slice(0, 120);
  } else if (rawTicket && typeof rawTicket === "object") {
    const t = rawTicket as Record<string, unknown>;
    inputSummary = String(
      t["subject"] ?? t["body"] ?? t["description"] ?? JSON.stringify(t)
    ).slice(0, 120);
  }

  const expectedBehavior =
    typeof item["expected_behavior"] === "string"
      ? item["expected_behavior"]
      : "(Not specified)";

  const failureModeTargeted =
    typeof item["failure_mode_targeted"] === "string"
      ? item["failure_mode_targeted"]
      : "(Unknown)";

  return { inputSummary, expectedBehavior, failureModeTargeted };
}

export function RegressionList({ regressions }: RegressionListProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <TestTube className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm font-semibold">
            Regression Tests
          </CardTitle>
          {regressions.length > 0 && (
            <Badge variant="secondary" className="ml-auto text-xs">
              {regressions.length}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {regressions.length === 0 ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>No regression tests generated yet.</span>
          </div>
        ) : (
          <ol className="space-y-3">
            {regressions.map((item, idx) => {
              const { inputSummary, expectedBehavior, failureModeTargeted } =
                extractRegressionItem(item);
              return (
                <motion.li
                  key={idx}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{
                    duration: 0.25,
                    delay: idx * 0.06,
                    ease: "easeOut",
                  }}
                  className="rounded-lg border border-border bg-muted/30 p-3"
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={cn(
                        "flex h-5 w-5 shrink-0 items-center justify-center rounded-full",
                        "bg-primary/10 text-primary text-xs font-semibold mt-0.5"
                      )}
                    >
                      {idx + 1}
                    </span>
                    <div className="flex-1 min-w-0 space-y-2">
                      {/* Input ticket summary */}
                      <p className="text-xs font-medium text-foreground leading-relaxed">
                        {inputSummary}
                        {inputSummary.length >= 120 && (
                          <span className="text-muted-foreground">…</span>
                        )}
                      </p>

                      <Separator />

                      {/* Expected behavior */}
                      <div className="flex items-start gap-1.5">
                        <span className="text-xs font-medium text-muted-foreground whitespace-nowrap mt-0.5">
                          Expected:
                        </span>
                        <span className="text-xs text-foreground leading-relaxed">
                          {expectedBehavior}
                        </span>
                      </div>

                      {/* Failure mode targeted */}
                      <div className="flex items-center gap-1.5">
                        <Target className="h-3 w-3 text-muted-foreground shrink-0" />
                        <Badge
                          variant="outline"
                          className="text-xs font-mono capitalize"
                        >
                          {failureModeTargeted.replace(/_/g, " ")}
                        </Badge>
                      </div>
                    </div>
                  </div>
                </motion.li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
