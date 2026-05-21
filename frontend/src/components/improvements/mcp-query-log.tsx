"use client";

import React from "react";
import { motion } from "framer-motion";
import { Terminal } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";

interface McpQueryLogProps {
  diagnosis: Record<string, unknown> | null;
}

interface LogEntry {
  prefix: string;
  value: string | null;
  color: string;
}

function buildLogEntries(diagnosis: Record<string, unknown>): LogEntry[] {
  const entries: LogEntry[] = [
    {
      prefix: "$ mcp_tool: query_phoenix_traces",
      value: null,
      color: "text-green-400",
    },
  ];

  if (diagnosis["evidence_summary"] != null) {
    entries.push({
      prefix: "Querying Phoenix traces...",
      value: String(diagnosis["evidence_summary"]),
      color: "text-green-300",
    });
  }

  if (diagnosis["failure_pattern"] != null) {
    entries.push({
      prefix: "Analyzing failure pattern...",
      value: String(diagnosis["failure_pattern"]),
      color: "text-yellow-300",
    });
  }

  if (diagnosis["root_cause"] != null) {
    entries.push({
      prefix: "Root cause identified:",
      value: String(diagnosis["root_cause"]),
      color: "text-cyan-300",
    });
  }

  if (diagnosis["confidence"] != null) {
    const raw = diagnosis["confidence"];
    const displayValue =
      typeof raw === "number"
        ? `${(raw * 100).toFixed(0)}%`
        : String(raw);
    entries.push({
      prefix: "Confidence:",
      value: displayValue,
      color: "text-purple-300",
    });
  }

  entries.push({
    prefix: "$ analysis complete",
    value: null,
    color: "text-green-400",
  });

  return entries;
}

export function McpQueryLog({ diagnosis }: McpQueryLogProps) {
  const entries: LogEntry[] = diagnosis
    ? buildLogEntries(diagnosis)
    : [
        {
          prefix: "Awaiting analysis...",
          value: "Run \"Analyze\" to start MCP-assisted diagnosis.",
          color: "text-gray-400",
        },
      ];

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-green-500" />
          <CardTitle className="text-sm font-semibold">MCP Query Log</CardTitle>
          <div className="ml-auto flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-red-500/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-yellow-500/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-green-500/70" />
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="bg-gray-950 rounded-b-lg">
          <ScrollArea className="h-56 w-full">
            <div className="p-4 font-mono text-xs leading-relaxed space-y-2">
              {entries.map((entry, idx) => (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{
                    duration: 0.3,
                    delay: idx * 0.12,
                    ease: "easeOut",
                  }}
                  className="flex flex-col gap-0.5"
                >
                  <span className={entry.color}>{entry.prefix}</span>
                  {entry.value != null && (
                    <span className="text-gray-300 pl-3 whitespace-pre-wrap">
                      {entry.value}
                    </span>
                  )}
                </motion.div>
              ))}
            </div>
          </ScrollArea>
        </div>
      </CardContent>
    </Card>
  );
}
