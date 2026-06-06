"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Activity,
  CheckCircle,
  BarChart3,
  Search,
  Wrench,
  FlaskConical,
  ShieldCheck,
  ArrowRight,
  Flame,
  Wifi,
  Tag,
  Clock,
  ChevronRight,
  PlayCircle,
  AlertTriangle,
  Database,
} from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { StatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type {
  ActivityEvent,
  ActivityEventKind,
  ConfigResponse,
  HealthResponse,
} from "@/lib/types";

// ─── Animation variants ────────────────────────────────────────────────────

const fadeUpVariants = {
  hidden: { opacity: 0, y: 24 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.45, ease: "easeOut", delay: i * 0.08 },
  }),
};

const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.1 } },
};

const childVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: "easeOut" } },
};

// ─── Self-Healing Loop data ────────────────────────────────────────────────

const LOOP_STAGES = [
  {
    label: "Trace",
    icon: Activity,
    description: "Capture spans via Phoenix",
    color: "text-violet-500",
    bg: "bg-violet-50 dark:bg-violet-950",
    border: "border-violet-200 dark:border-violet-800",
  },
  {
    label: "Evaluate",
    icon: CheckCircle,
    description: "Score every run",
    color: "text-blue-500",
    bg: "bg-blue-50 dark:bg-blue-950",
    border: "border-blue-200 dark:border-blue-800",
  },
  {
    label: "Aggregate",
    icon: BarChart3,
    description: "Cluster failure patterns",
    color: "text-cyan-500",
    bg: "bg-cyan-50 dark:bg-cyan-950",
    border: "border-cyan-200 dark:border-cyan-800",
  },
  {
    label: "Diagnose",
    icon: Search,
    description: "Root-cause analysis",
    color: "text-amber-500",
    bg: "bg-amber-50 dark:bg-amber-950",
    border: "border-amber-200 dark:border-amber-800",
  },
  {
    label: "Repair",
    icon: Wrench,
    description: "Generate patch proposals",
    color: "text-orange-500",
    bg: "bg-orange-50 dark:bg-orange-950",
    border: "border-orange-200 dark:border-orange-800",
  },
  {
    label: "Experiment",
    icon: FlaskConical,
    description: "A/B test the fix",
    color: "text-pink-500",
    bg: "bg-pink-50 dark:bg-pink-950",
    border: "border-pink-200 dark:border-pink-800",
  },
  {
    label: "Gate",
    icon: ShieldCheck,
    description: "Promote or reject",
    color: "text-green-500",
    bg: "bg-green-50 dark:bg-green-950",
    border: "border-green-200 dark:border-green-800",
  },
] as const;

// ─── Activity feed visual mapping ─────────────────────────────────────────

const ACTIVITY_ICON: Record<ActivityEventKind, React.ElementType> = {
  agent_run: Flame,
  failure: AlertTriangle,
  improvement_trigger: Wrench,
  experiment: FlaskConical,
  release_decision: ShieldCheck,
};

const ACTIVITY_COLOR: Record<ActivityEventKind, string> = {
  agent_run: "text-violet-500",
  failure: "text-amber-500",
  improvement_trigger: "text-blue-500",
  experiment: "text-pink-500",
  release_decision: "text-green-500",
};

// ─── Main component ────────────────────────────────────────────────────────

export default function HomePage() {
  const router = useRouter();
  const [seedStatus, setSeedStatus] = useState<
    "idle" | "loading" | "success" | "error"
  >("idle");
  const [seedMessage, setSeedMessage] = useState<string>("");

  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(true);
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);
  const [configData, setConfigData] = useState<ConfigResponse | null>(null);
  const [latestExperiment, setLatestExperiment] = useState<{
    experiment_id: string;
    status: string;
  } | null>(null);

  useEffect(() => {
    async function load() {
      setEventsLoading(true);
      const [actRes, healthRes, configRes, expRes] = await Promise.all([
        api.activity.list(5),
        api.health.check(),
        api.config.get(),
        api.experiments.list(),
      ]);
      if (actRes.ok && actRes.data) {
        setEvents(actRes.data as ActivityEvent[]);
      }
      if (healthRes.ok && healthRes.data) {
        setHealthData(healthRes.data as HealthResponse);
      }
      if (configRes.ok && configRes.data) {
        setConfigData(configRes.data as ConfigResponse);
      }
      if (expRes.ok && expRes.data) {
        const items = (
          expRes.data as { items?: { experiment_id: string; status: string }[] }
        ).items;
        if (items && items.length > 0) {
          setLatestExperiment(items[0]);
        }
      }
      setEventsLoading(false);
    }
    void load();
  }, []);

  async function handleSeedDemo() {
    setSeedStatus("loading");
    setSeedMessage("");
    try {
      const result = await api.demo.seed();
      if (result.ok) {
        setSeedStatus("success");
        setSeedMessage("Demo data seeded successfully.");
      } else {
        setSeedStatus("error");
        setSeedMessage(result.error ?? "Seed failed.");
      }
    } catch {
      setSeedStatus("error");
      setSeedMessage("Could not reach the backend.");
    }
  }

  return (
    <div className="space-y-10">
      {/* Page Header */}
      <PageHeader
        title="Dashboard"
        description="Self-healing agent overview"
        actions={
          <StatusBadge status="success" label="System Online" pulse />
        }
      />

      {/* ── Hero Section ────────────────────────────────────────────── */}
      <motion.section
        custom={0}
        initial="hidden"
        animate="visible"
        variants={fadeUpVariants}
        className="rounded-xl border bg-gradient-to-br from-background via-muted/30 to-background px-8 py-10 text-center"
      >
        <div className="mx-auto flex max-w-2xl flex-col items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-primary shadow-lg">
            <Flame className="h-8 w-8 text-primary-foreground" />
          </div>
          <h2 className="text-4xl font-extrabold tracking-tight">
            PhoenixLoop
          </h2>
          <p className="text-lg text-muted-foreground">
            A Gemini support agent that detects its own failures through Phoenix
            and fixes itself with evidence.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-2 pt-1">
            <StatusBadge status="info" label="Powered by Gemini" />
            <StatusBadge status="info" label="Traced by Phoenix" />
            <StatusBadge status="success" label="Self-Healing" pulse />
          </div>
        </div>
      </motion.section>

      {/* ── Self-Healing Loop Diagram ──────────────────────────────── */}
      <motion.section
        custom={1}
        initial="hidden"
        animate="visible"
        variants={fadeUpVariants}
      >
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Self-Healing Loop
        </h3>
        <Card>
          <CardContent className="pt-6">
            <motion.div
              variants={containerVariants}
              initial="hidden"
              animate="visible"
              className="flex flex-wrap items-start justify-center gap-2"
            >
              {LOOP_STAGES.map((stage, idx) => {
                const Icon = stage.icon;
                const isLast = idx === LOOP_STAGES.length - 1;
                return (
                  <React.Fragment key={stage.label}>
                    <motion.div
                      variants={childVariants}
                      className="flex flex-col items-center gap-2"
                    >
                      <div
                        className={cn(
                          "flex h-12 w-12 items-center justify-center rounded-xl border-2",
                          stage.bg,
                          stage.border
                        )}
                      >
                        <Icon className={cn("h-5 w-5", stage.color)} />
                      </div>
                      <span className="text-xs font-semibold text-foreground">
                        {stage.label}
                      </span>
                      <span className="max-w-[72px] text-center text-[10px] leading-tight text-muted-foreground">
                        {stage.description}
                      </span>
                    </motion.div>
                    {!isLast && (
                      <motion.div
                        variants={childVariants}
                        className="mt-4 text-muted-foreground/40"
                      >
                        <ChevronRight className="h-5 w-5" />
                      </motion.div>
                    )}
                  </React.Fragment>
                );
              })}
            </motion.div>
          </CardContent>
        </Card>
      </motion.section>

      {/* ── System Health Cards ────────────────────────────────────── */}
      <motion.section
        custom={2}
        initial="hidden"
        animate="visible"
        variants={fadeUpVariants}
      >
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          System Health
        </h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            title="Phoenix Connected"
            value={
              healthData
                ? healthData.checks.phoenix.ok
                  ? "Connected"
                  : "Disconnected"
                : "…"
            }
            description={
              healthData
                ? healthData.checks.phoenix.detail.slice(0, 40)
                : "Probing…"
            }
            icon={<Wifi className="h-4 w-4" />}
          />
          <StatCard
            title="Agent Version"
            value={configData?.agent_version ?? "…"}
            description={configData?.agent_name ?? ""}
            icon={<Flame className="h-4 w-4" />}
          />
          <StatCard
            title="Active Prompt"
            value={configData?.active_prompt_version ?? "…"}
            description={configData ? `model: ${configData.gemini_model}` : ""}
            icon={<Tag className="h-4 w-4" />}
          />
          <StatCard
            title="Last Experiment"
            value={
              latestExperiment
                ? `${latestExperiment.experiment_id.slice(0, 8)}…`
                : "None yet"
            }
            description={latestExperiment?.status ?? ""}
            icon={<Clock className="h-4 w-4" />}
          />
        </div>
      </motion.section>

      {/* ── Quick-Start Actions ────────────────────────────────────── */}
      <motion.section
        custom={3}
        initial="hidden"
        animate="visible"
        variants={fadeUpVariants}
      >
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Quick Start
        </h3>
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-wrap items-center gap-3">
              <Button
                onClick={handleSeedDemo}
                disabled={seedStatus === "loading"}
                className="gap-2"
              >
                <Database className="h-4 w-4" />
                {seedStatus === "loading" ? "Seeding…" : "Seed Demo Data"}
              </Button>
              <Button
                variant="outline"
                onClick={() => router.push("/conversation")}
                className="gap-2"
              >
                <PlayCircle className="h-4 w-4" />
                Run a Scenario
              </Button>
              <Button
                variant="secondary"
                onClick={() => router.push("/activity/failures")}
                className="gap-2"
              >
                <AlertTriangle className="h-4 w-4" />
                View Failures
              </Button>
            </div>

            {/* Seed feedback */}
            {seedStatus !== "idle" && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-4"
              >
                <Alert
                  variant={seedStatus === "error" ? "destructive" : "default"}
                  className={cn(
                    seedStatus === "success" &&
                      "border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-300"
                  )}
                >
                  {seedStatus === "success" && (
                    <CheckCircle className="h-4 w-4" />
                  )}
                  {seedStatus === "error" && (
                    <AlertTriangle className="h-4 w-4" />
                  )}
                  <AlertDescription>{seedMessage}</AlertDescription>
                </Alert>
              </motion.div>
            )}
          </CardContent>
        </Card>
      </motion.section>

      {/* ── Recent Activity Feed ───────────────────────────────────── */}
      <motion.section
        custom={4}
        initial="hidden"
        animate="visible"
        variants={fadeUpVariants}
      >
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Recent Activity
        </h3>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold">
              Last 5 events
            </CardTitle>
          </CardHeader>
          <CardContent className="pb-4">
            {eventsLoading ? (
              <p className="py-3 text-sm text-muted-foreground">Loading…</p>
            ) : events.length === 0 ? (
              <div className="py-8 text-center">
                <p className="mb-3 text-sm text-muted-foreground">
                  No activity yet.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => router.push("/conversation")}
                >
                  Run a scenario
                </Button>
              </div>
            ) : (
              <motion.ul
                variants={containerVariants}
                initial="hidden"
                animate="visible"
                className="divide-y"
              >
                {events.map((event) => {
                  const Icon = ACTIVITY_ICON[event.kind];
                  const iconColor = ACTIVITY_COLOR[event.kind];
                  const route = event.target_route;
                  return (
                    <motion.li
                      key={event.event_id}
                      variants={childVariants}
                      className={cn(
                        "flex items-start gap-3 py-3 first:pt-0 last:pb-0",
                        route &&
                          "-mx-2 cursor-pointer rounded px-2 transition-colors hover:bg-muted/30"
                      )}
                      onClick={route ? () => router.push(route) : undefined}
                    >
                      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted">
                        <Icon className={cn("h-4 w-4", iconColor)} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium leading-tight">
                          {event.title}
                        </p>
                        {event.subtitle && (
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            {event.subtitle}
                          </p>
                        )}
                      </div>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {new Date(event.timestamp).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </motion.li>
                  );
                })}
              </motion.ul>
            )}
            <Separator className="mt-4" />
            <div className="mt-3 flex justify-end">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => router.push("/activity/runs")}
                className="gap-1 text-xs"
              >
                View all activity
                <ArrowRight className="h-3 w-3" />
              </Button>
            </div>
          </CardContent>
        </Card>
      </motion.section>
    </div>
  );
}
