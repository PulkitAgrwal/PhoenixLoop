"use client";

import { useState } from "react";
import { Copy } from "lucide-react";
import { createTwoFilesPatch } from "diff";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { PromptDiffUnified } from "./prompt-diff-unified";
import { PromptDiffAnnotated } from "./prompt-diff-annotated";

interface Props {
  baseline: string;
  candidate: string;
  defaultTab?: "diff" | "full";
  showCopy?: boolean;
}

export function PromptDiffView({
  baseline,
  candidate,
  defaultTab = "diff",
  showCopy = true,
}: Props) {
  const [tab, setTab] = useState<"diff" | "full">(defaultTab);

  async function handleCopy() {
    const text =
      tab === "full"
        ? candidate
        : createTwoFilesPatch("baseline", "candidate", baseline, candidate);
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // browser blocked clipboard — silent no-op
    }
  }

  return (
    <Tabs value={tab} onValueChange={(v) => setTab(v as "diff" | "full")}>
      <div className="flex items-center justify-between mb-2">
        <TabsList>
          <TabsTrigger value="diff">Diff</TabsTrigger>
          <TabsTrigger value="full">Full</TabsTrigger>
        </TabsList>
        {showCopy && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleCopy}
            title={
              tab === "full" ? "Copy candidate prompt" : "Copy unified diff"
            }
          >
            <Copy className="h-3.5 w-3.5 mr-1.5" />
            Copy
          </Button>
        )}
      </div>
      <TabsContent value="diff">
        <div className="max-h-[400px] overflow-y-auto rounded-md border bg-muted/20 p-2">
          <PromptDiffUnified baseline={baseline} candidate={candidate} />
        </div>
      </TabsContent>
      <TabsContent value="full">
        <div className="max-h-[400px] overflow-y-auto rounded-md border bg-muted/20 p-2">
          <PromptDiffAnnotated baseline={baseline} candidate={candidate} />
        </div>
      </TabsContent>
    </Tabs>
  );
}
