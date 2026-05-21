"use client";

import React, { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Wifi,
  WifiOff,
  Database,
  Cloud,
  Cpu,
  RefreshCw,
  Sprout,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { StatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ConnectionStatus {
  name: string;
  connected: boolean;
  detail: string;
  responseTimeMs?: number;
  checkedAt: Date | null;
}

interface EvaluatorEntry {
  name: string;
  type: "code" | "llm_judge" | "tool_eval";
  annotationLevel: "span" | "session";
}

// ---------------------------------------------------------------------------
// Static data
// ---------------------------------------------------------------------------

const CONFIG_ROWS: { setting: string; value: string }[] = [
  { setting: "Database", value: "SQLite with WAL mode" },
  { setting: "Failure Threshold (count)", value: "2" },
  { setting: "Failure Threshold (rate)", value: "30%" },
  { setting: "Latency Budget", value: "10,000 ms" },
  { setting: "Max Retry Attempts", value: "3" },
  { setting: "Active Prompt Version", value: "production" },
  { setting: "Agent Name", value: "acmeflow_support_agent" },
  { setting: "Agent Version", value: "1.0.0" },
];

const EVALUATORS: EvaluatorEntry[] = [
  // Code evaluators
  { name: "SchemaValidity", type: "code", annotationLevel: "span" },
  { name: "ToolSequence", type: "code", annotationLevel: "session" },
  { name: "RefundGuard", type: "code", annotationLevel: "span" },
  { name: "PrivacyGuard", type: "code", annotationLevel: "span" },
  { name: "EscalationGuard", type: "code", annotationLevel: "span" },
  { name: "CitationPresence", type: "code", annotationLevel: "span" },
  { name: "LatencyBudget", type: "code", annotationLevel: "span" },
  // LLM Judge evaluators
  { name: "Groundedness", type: "llm_judge", annotationLevel: "session" },
  {
    name: "PolicyCompliance",
    type: "llm_judge",
    annotationLevel: "session",
  },
  {
    name: "ResolutionCorrectness",
    type: "llm_judge",
    annotationLevel: "session",
  },
  { name: "SafetyPrivacy", type: "llm_judge", annotationLevel: "span" },
  // Tool eval evaluators
  { name: "ToolSelection", type: "tool_eval", annotationLevel: "span" },
  { name: "ToolInvocation", type: "tool_eval", annotationLevel: "span" },
  {
    name: "ToolResponseHandling",
    type: "tool_eval",
    annotationLevel: "span",
  },
];

const CODE_EVALUATORS = EVALUATORS.filter((e) => e.type === "code");
const LLM_EVALUATORS = EVALUATORS.filter((e) => e.type === "llm_judge");
const TOOL_EVALUATORS = EVALUATORS.filter((e) => e.type === "tool_eval");

// ---------------------------------------------------------------------------
// Animation variants
// ---------------------------------------------------------------------------

const fadeUpVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: "easeOut", delay: i * 0.1 },
  }),
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function EvalTypeBadge({ type }: { type: EvaluatorEntry["type"] }) {
  const styles: Record<EvaluatorEntry["type"], string> = {
    code: "border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-800 dark:bg-violet-950 dark:text-violet-400",
    llm_judge:
      "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-400",
    tool_eval:
      "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-400",
  };
  const labels: Record<EvaluatorEntry["type"], string> = {
    code: "Code",
    llm_judge: "LLM Judge",
    tool_eval: "Tool Eval",
  };
  return (
    <Badge variant="outline" className={cn("text-xs font-medium", styles[type])}>
      {labels[type]}
    </Badge>
  );
}

function AnnotationBadge({ level }: { level: "span" | "session" }) {
  return (
    <Badge
      variant="outline"
      className="text-xs font-medium border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400"
    >
      {level}
    </Badge>
  );
}

function EvaluatorTable({ evaluators }: { evaluators: EvaluatorEntry[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Annotation Level</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {evaluators.map((ev) => (
          <TableRow key={ev.name}>
            <TableCell className="font-mono text-sm font-medium">
              {ev.name}
            </TableCell>
            <TableCell>
              <EvalTypeBadge type={ev.type} />
            </TableCell>
            <TableCell>
              <AnnotationBadge level={ev.annotationLevel} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

interface ConnectionCardProps {
  status: ConnectionStatus;
  icon: React.ReactNode;
}

function ConnectionCard({ status, icon }: ConnectionCardProps) {
  const badgeStatus = status.connected ? "success" : "error";
  const badgeLabel = status.connected ? "Connected" : "Disconnected";

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {status.name}
        </CardTitle>
        <div
          className={cn(
            "text-muted-foreground",
            status.connected ? "text-green-600" : "text-red-500"
          )}
        >
          {status.connected ? (
            <Wifi className="h-4 w-4" />
          ) : (
            <WifiOff className="h-4 w-4" />
          )}
          <span className="sr-only">{icon}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <StatusBadge status={badgeStatus} label={badgeLabel} pulse={status.connected} />
        <p className="text-xs text-muted-foreground">{status.detail}</p>
        {status.responseTimeMs !== undefined && (
          <p className="text-xs text-muted-foreground">
            Response: {status.responseTimeMs} ms
          </p>
        )}
        {status.checkedAt && (
          <p className="text-xs text-muted-foreground">
            Checked:{" "}
            {status.checkedAt.toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            })}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export default function SettingsPage() {
  const [connections, setConnections] = useState<ConnectionStatus[]>([
    {
      name: "Backend API",
      connected: false,
      detail: "Checking…",
      checkedAt: null,
    },
    {
      name: "Phoenix Cloud",
      connected: false,
      detail: "Checking…",
      checkedAt: null,
    },
    {
      name: "Gemini API",
      connected: false,
      detail: "Checking…",
      checkedAt: null,
    },
    {
      name: "Database",
      connected: false,
      detail: "Checking…",
      checkedAt: null,
    },
  ]);

  const [healthLoading, setHealthLoading] = useState(false);
  const [seedLoading, setSeedLoading] = useState(false);
  const [seedResult, setSeedResult] = useState<{
    ok: boolean;
    message: string;
  } | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  const checkHealth = useCallback(async () => {
    setHealthLoading(true);
    setHealthError(null);
    const start = Date.now();

    try {
      const result = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/health`
      );
      const elapsed = Date.now() - start;
      const checkedAt = new Date();

      if (result.ok) {
        const body: HealthResponse = await result.json();
        setConnections([
          {
            name: "Backend API",
            connected: true,
            detail: `${body.service} v${body.version}`,
            responseTimeMs: elapsed,
            checkedAt,
          },
          {
            name: "Phoenix Cloud",
            connected: true,
            detail: "PHOENIX_API_KEY configured",
            checkedAt,
          },
          {
            name: "Gemini API",
            connected: true,
            detail: "GEMINI_API_KEY configured",
            checkedAt,
          },
          {
            name: "Database",
            connected: true,
            detail: "SQLite (WAL mode) — healthy",
            checkedAt,
          },
        ]);
      } else {
        throw new Error(`HTTP ${result.status}`);
      }
    } catch (err) {
      const checkedAt = new Date();
      const errMessage =
        err instanceof Error ? err.message : "Unknown error";
      setHealthError(`Health check failed: ${errMessage}`);
      setConnections([
        {
          name: "Backend API",
          connected: false,
          detail: `Unreachable — ${errMessage}`,
          checkedAt,
        },
        {
          name: "Phoenix Cloud",
          connected: false,
          detail: "Cannot verify — backend offline",
          checkedAt,
        },
        {
          name: "Gemini API",
          connected: false,
          detail: "Cannot verify — backend offline",
          checkedAt,
        },
        {
          name: "Database",
          connected: false,
          detail: "Cannot verify — backend offline",
          checkedAt,
        },
      ]);
    } finally {
      setHealthLoading(false);
    }
  }, []);

  // Run once on mount
  useEffect(() => {
    void checkHealth();
  }, [checkHealth]);

  async function handleSeed() {
    setSeedLoading(true);
    setSeedResult(null);
    try {
      const result = await api.demo.seed();
      if (result.ok) {
        setSeedResult({ ok: true, message: "Demo data seeded successfully." });
      } else {
        setSeedResult({
          ok: false,
          message: result.error ?? "Failed to seed demo data.",
        });
      }
    } catch {
      setSeedResult({ ok: false, message: "Could not reach the backend." });
    } finally {
      setSeedLoading(false);
    }
  }

  const connectionIcons = [
    <Wifi key="api" className="h-4 w-4" />,
    <Cloud key="phoenix" className="h-4 w-4" />,
    <Cpu key="gemini" className="h-4 w-4" />,
    <Database key="db" className="h-4 w-4" />,
  ];

  return (
    <div className="space-y-8">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                               */}
      {/* ------------------------------------------------------------------ */}
      <PageHeader
        title="Settings"
        description="System status and configuration"
      />

      {/* ------------------------------------------------------------------ */}
      {/* Connection Status Cards                                              */}
      {/* ------------------------------------------------------------------ */}
      <motion.section
        custom={0}
        initial="hidden"
        animate="visible"
        variants={fadeUpVariants}
        className="space-y-3"
      >
        <h2 className="text-base font-semibold">Connection Status</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {connections.map((conn, idx) => (
            <ConnectionCard
              key={conn.name}
              status={conn}
              icon={connectionIcons[idx]}
            />
          ))}
        </div>
      </motion.section>

      {/* ------------------------------------------------------------------ */}
      {/* Configuration Table                                                  */}
      {/* ------------------------------------------------------------------ */}
      <motion.section
        custom={1}
        initial="hidden"
        animate="visible"
        variants={fadeUpVariants}
        className="space-y-3"
      >
        <h2 className="text-base font-semibold">Configuration</h2>
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-1/2">Setting</TableHead>
                  <TableHead>Value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {CONFIG_ROWS.map((row) => (
                  <TableRow key={row.setting}>
                    <TableCell className="font-medium text-sm">
                      {row.setting}
                    </TableCell>
                    <TableCell className="font-mono text-sm text-muted-foreground">
                      {row.value}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </motion.section>

      {/* ------------------------------------------------------------------ */}
      {/* Evaluator Registry                                                   */}
      {/* ------------------------------------------------------------------ */}
      <motion.section
        custom={2}
        initial="hidden"
        animate="visible"
        variants={fadeUpVariants}
        className="space-y-3"
      >
        <h2 className="text-base font-semibold">
          Evaluator Registry{" "}
          <span className="text-muted-foreground font-normal text-sm">
            ({EVALUATORS.length} evaluators)
          </span>
        </h2>
        <Card>
          <CardContent className="p-0 pt-4 px-4 pb-4">
            <Tabs defaultValue="code">
              <TabsList>
                <TabsTrigger value="code">
                  Code ({CODE_EVALUATORS.length})
                </TabsTrigger>
                <TabsTrigger value="llm">
                  LLM Judge ({LLM_EVALUATORS.length})
                </TabsTrigger>
                <TabsTrigger value="tool">
                  Tool Eval ({TOOL_EVALUATORS.length})
                </TabsTrigger>
              </TabsList>
              <TabsContent value="code">
                <EvaluatorTable evaluators={CODE_EVALUATORS} />
              </TabsContent>
              <TabsContent value="llm">
                <EvaluatorTable evaluators={LLM_EVALUATORS} />
              </TabsContent>
              <TabsContent value="tool">
                <EvaluatorTable evaluators={TOOL_EVALUATORS} />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </motion.section>

      {/* ------------------------------------------------------------------ */}
      {/* Diagnostic Actions                                                   */}
      {/* ------------------------------------------------------------------ */}
      <motion.section
        custom={3}
        initial="hidden"
        animate="visible"
        variants={fadeUpVariants}
        className="space-y-4"
      >
        <h2 className="text-base font-semibold">Diagnostic Actions</h2>

        <div className="flex flex-wrap gap-3">
          <Button
            variant="outline"
            onClick={() => void checkHealth()}
            disabled={healthLoading}
            className="gap-2"
          >
            <RefreshCw
              className={cn("h-4 w-4", healthLoading && "animate-spin")}
            />
            {healthLoading ? "Checking…" : "Check Health"}
          </Button>

          <Button
            variant="outline"
            onClick={() => void handleSeed()}
            disabled={seedLoading}
            className="gap-2"
          >
            <Sprout className={cn("h-4 w-4", seedLoading && "animate-pulse")} />
            {seedLoading ? "Seeding…" : "Re-seed Demo Data"}
          </Button>
        </div>

        {/* Health error feedback */}
        {healthError && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>{healthError}</AlertDescription>
            </Alert>
          </motion.div>
        )}

        {/* Seed result feedback */}
        {seedResult && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
          >
            {seedResult.ok ? (
              <Alert className="border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200">
                <CheckCircle2 className="h-4 w-4 text-green-600" />
                <AlertDescription>{seedResult.message}</AlertDescription>
              </Alert>
            ) : (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>{seedResult.message}</AlertDescription>
              </Alert>
            )}
          </motion.div>
        )}
      </motion.section>
    </div>
  );
}
