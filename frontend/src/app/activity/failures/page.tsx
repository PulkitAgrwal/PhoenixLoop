"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  ShieldAlert,
  Activity,
  ArrowRight,
} from "lucide-react";
import { StatCard } from "@/components/shared/stat-card";
import { ChartSkeleton, TableSkeleton } from "@/components/shared/loading-skeleton";
import { FailureChart } from "@/components/failures/failure-chart";
import { FailureTable } from "@/components/failures/failure-table";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { FailureAggregate } from "@/lib/types";

const THRESHOLD = 2;

const CRITICAL_FAILURE_TYPES = new Set<string>([
  "privacy_leak",
  "wrong_escalation",
]);

const fadeUpVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease: "easeOut", delay: i * 0.08 },
  }),
};

export default function FailuresPage() {
  const router = useRouter();

  const [failures, setFailures] = useState<FailureAggregate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [diagnosingKey, setDiagnosingKey] = useState<string | null>(null);
  const [diagnoseError, setDiagnoseError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await api.evals.getFailures(true);
        if (cancelled) return;
        if (!result.ok) {
          setError(result.error ?? "Failed to load failure data.");
        } else {
          const items = Array.isArray(result.data)
            ? (result.data as FailureAggregate[])
            : [];
          setFailures(items);
        }
      } catch {
        if (!cancelled) {
          setError("Could not reach the backend. Is it running?");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleDiagnose(failureKey: string) {
    setDiagnosingKey(failureKey);
    setDiagnoseError(null);
    try {
      const result = await api.improvements.create(failureKey);
      if (!result.ok) {
        setDiagnoseError(
          result.error ?? "Failed to create improvement trigger."
        );
      } else {
        router.push("/healing/improvements");
      }
    } catch {
      setDiagnoseError("Could not reach the backend.");
    } finally {
      setDiagnosingKey(null);
    }
  }

  // Derived stats
  const totalActive = failures.length;
  const aboveThreshold = failures.filter(
    (f) => f.occurrence_count >= THRESHOLD
  ).length;
  const criticalCount = failures.filter((f) =>
    CRITICAL_FAILURE_TYPES.has(f.failure_key)
  ).length;

  return (
    <div className="space-y-8">
      {/* Stats Row */}
      <motion.section
        custom={0}
        initial="hidden"
        animate="visible"
        variants={fadeUpVariants}
        className="grid grid-cols-1 gap-4 sm:grid-cols-3"
      >
        <StatCard
          title="Total Active Failures"
          value={loading ? "—" : totalActive}
          description="Active failure aggregates"
          icon={<Activity className="h-4 w-4" />}
        />
        <StatCard
          title="Above Threshold"
          value={loading ? "—" : aboveThreshold}
          description={`Occurrence count ≥ ${THRESHOLD}`}
          icon={<AlertTriangle className="h-4 w-4" />}
        />
        <StatCard
          title="Critical Failures"
          value={loading ? "—" : criticalCount}
          description="privacy_leak or wrong_escalation"
          icon={<ShieldAlert className="h-4 w-4" />}
        />
      </motion.section>

      {/* Global error */}
      {error && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        </motion.div>
      )}

      {/* Diagnose action error */}
      {diagnoseError && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{diagnoseError}</AlertDescription>
          </Alert>
        </motion.div>
      )}

      {/* Chart Section */}
      <motion.section
        custom={1}
        initial="hidden"
        animate="visible"
        variants={fadeUpVariants}
      >
        {loading ? (
          <ChartSkeleton />
        ) : failures.length === 0 && !error ? null : failures.length > 0 ? (
          <FailureChart failures={failures} threshold={THRESHOLD} />
        ) : null}
      </motion.section>

      {/* Table Section */}
      <motion.section
        custom={2}
        initial="hidden"
        animate="visible"
        variants={fadeUpVariants}
      >
        {loading ? (
          <TableSkeleton rows={5} />
        ) : !error && failures.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16 text-center gap-3">
            <Activity className="h-10 w-10 text-muted-foreground/40" />
            <p className="text-muted-foreground text-sm max-w-xs">
              No failures detected yet. Run some conversations first.
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/conversation")}
              className="gap-1.5"
            >
              Go to Conversations
              <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        ) : failures.length > 0 ? (
          <FailureTable
            failures={failures}
            threshold={THRESHOLD}
            onDiagnose={handleDiagnose}
            diagnosingKey={diagnosingKey}
          />
        ) : null}
      </motion.section>
    </div>
  );
}
