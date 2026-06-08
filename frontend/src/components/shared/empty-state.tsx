"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

interface EmptyStateProps {
  title: string;
  description: string;
  showSeedButton?: boolean;
}

export function EmptyState({
  title,
  description,
  showSeedButton = true,
}: EmptyStateProps) {
  const [seeding, setSeeding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function runSeed() {
    setSeeding(true);
    setError(null);
    try {
      const res = await api.demo.seed();
      if (!res.ok) {
        setError(res.error ?? "Seed failed");
        return;
      }
      setDone(true);
      setTimeout(() => window.location.reload(), 900);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Seed failed");
    } finally {
      setSeeding(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-md flex-col items-center justify-center gap-4 px-6 py-16 text-center">
      <h3 className="text-display-sm text-ink-strong">{title}</h3>
      <p className="text-body-sm text-body">{description}</p>
      {showSeedButton && (
        <Button
          variant="primary"
          onClick={runSeed}
          disabled={seeding || done}
          aria-label="Populate demo data"
        >
          {done ? "Seeded — reloading…" : seeding ? "Seeding…" : "Run seed"}
        </Button>
      )}
      {error && (
        <p role="alert" className="text-caption text-fail">
          {error}
        </p>
      )}
    </div>
  );
}
