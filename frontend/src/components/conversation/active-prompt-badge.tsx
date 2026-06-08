"use client";

import { useActivePrompt } from "@/lib/hooks/use-active-prompt";

export function ActivePromptBadge() {
  const { info, loading, error } = useActivePrompt();

  if (loading) {
    return (
      <span className="inline-flex items-center gap-2 rounded-pill border border-hairline bg-canvas-soft px-3 py-1 text-caption text-mute">
        <span className="h-1.5 w-1.5 animate-pulse-dot rounded-pill bg-mute" />
        Loading active prompt...
      </span>
    );
  }
  if (error || !info) {
    return (
      <span className="inline-flex items-center gap-2 rounded-pill border border-fail/40 bg-fail/[0.06] px-3 py-1 text-caption text-fail">
        Production prompt unavailable
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-2 rounded-pill border border-hairline bg-canvas-soft px-3 py-1 text-caption text-ink-strong"
      title={`Active prompt version ${info.versionId}`}
    >
      <span className="h-1.5 w-1.5 rounded-pill bg-brand" aria-hidden />
      Production prompt {info.versionLabel}
    </span>
  );
}
