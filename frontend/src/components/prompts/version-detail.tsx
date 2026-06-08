"use client";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Pencil, FlaskConical } from "lucide-react";
import { PromptVersion } from "@/lib/types";
import { PhoenixDeepLink } from "@/components/shared/phoenix-deep-link";

interface Props {
  version: PromptVersion;
  isActive: boolean;
  onEdit: () => void;
  onLaunchExperiment: () => void;
  experimentLoading: boolean;
}

export function VersionDetail({
  version,
  isActive,
  onEdit,
  onLaunchExperiment,
  experimentLoading,
}: Props) {
  const description = (version.metadata_json?.description as string | undefined) ?? null;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <CardTitle className="text-base font-semibold flex items-center gap-2 font-mono">
                {version.version_tag}
                {isActive && (
                  <Badge
                    variant="outline"
                    className="text-xs border-emerald-300 bg-emerald-50 text-emerald-700"
                  >
                    ACTIVE
                  </Badge>
                )}
                <PhoenixDeepLink promptId={version.prompt_version_id} />
              </CardTitle>
              <div className="text-xs text-muted-foreground mt-1 space-y-0.5">
                <div>
                  source: {version.source.replace("_", " ")} · created{" "}
                  {new Date(version.created_at).toLocaleString()}
                </div>
                {version.parent_version_id && (
                  <div>
                    parent:{" "}
                    <span className="font-mono">
                      {version.parent_version_id.slice(0, 8)}…
                    </span>
                  </div>
                )}
                {description && (
                  <div className="text-foreground/80">
                    description: {description}
                  </div>
                )}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {isActive ? (
                <Button
                  size="sm"
                  variant="default"
                  onClick={onEdit}
                  className="gap-1.5"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Edit
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={onLaunchExperiment}
                  disabled={experimentLoading}
                  className="gap-1.5"
                >
                  <FlaskConical className="h-3.5 w-3.5" />
                  {experimentLoading ? "Starting…" : "Run Experiment"}
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">Prompt Text</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="max-h-[60vh] overflow-y-auto rounded-md border bg-muted/20 p-3">
            <pre className="font-mono text-xs leading-relaxed whitespace-pre-wrap break-words">
              {version.prompt_text}
            </pre>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
