"use client";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { PromptVersion } from "@/lib/types";
import { motion } from "framer-motion";

interface Props {
  versions: PromptVersion[];
  activeVersionId: string | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const SOURCE_COLOR: Record<string, string> = {
  seed: "border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-800 dark:bg-violet-950 dark:text-violet-400",
  diagnosis_proposal:
    "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-400",
  manual:
    "border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-400",
};

export function VersionList({
  versions,
  activeVersionId,
  selectedId,
  onSelect,
}: Props) {
  if (versions.length === 0) {
    return (
      <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
        No prompt versions yet.
      </div>
    );
  }

  return (
    <ul className="space-y-1">
      {versions.map((v, idx) => {
        const isActive = v.prompt_version_id === activeVersionId;
        const isSelected = v.prompt_version_id === selectedId;
        return (
          <motion.li
            key={v.prompt_version_id}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.18, delay: idx * 0.03 }}
          >
            <button
              type="button"
              onClick={() => onSelect(v.prompt_version_id)}
              className={cn(
                "w-full text-left rounded-md border p-3 transition-colors",
                isSelected
                  ? "border-primary bg-primary/5"
                  : "border-border hover:bg-muted/50",
              )}
            >
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "h-2 w-2 rounded-full",
                    isActive ? "bg-emerald-500" : "bg-muted-foreground/30",
                  )}
                />
                <span className="font-mono text-sm">{v.version_tag}</span>
                {isActive && (
                  <Badge
                    variant="outline"
                    className="text-[10px] border-emerald-300 bg-emerald-50 text-emerald-700"
                  >
                    ACTIVE
                  </Badge>
                )}
              </div>
              <div className="mt-1.5 flex items-center gap-2">
                <Badge
                  variant="outline"
                  className={cn("text-[10px]", SOURCE_COLOR[v.source])}
                >
                  {v.source.replace("_", " ")}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {new Date(v.created_at).toLocaleDateString()}
                </span>
              </div>
            </button>
          </motion.li>
        );
      })}
    </ul>
  );
}
