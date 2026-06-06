"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import { ChevronDown, ChevronRight, ExternalLink } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

interface EvidenceCardProps {
  exampleRunIds: string[];
  failureKey: string;
}

export function EvidenceCard({ exampleRunIds, failureKey }: EvidenceCardProps) {
  const [isOpen, setIsOpen] = useState(exampleRunIds.length <= 3);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
    >
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-sm font-semibold">
              Failing Evidence
            </CardTitle>
            <Badge
              variant="outline"
              className="font-mono text-xs max-w-[240px] truncate"
              title={failureKey}
            >
              {failureKey}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          {exampleRunIds.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No example runs recorded.
            </p>
          ) : (
            <Collapsible open={isOpen} onOpenChange={setIsOpen}>
              <div className="flex flex-col gap-1">
                {/* Always show the first 3 */}
                {exampleRunIds.slice(0, 3).map((runId) => (
                  <RunIdLink key={runId} runId={runId} />
                ))}

                {/* Show "show more" if more than 3 */}
                {exampleRunIds.length > 3 && (
                  <>
                    <CollapsibleContent className="flex flex-col gap-1">
                      {exampleRunIds.slice(3).map((runId) => (
                        <RunIdLink key={runId} runId={runId} />
                      ))}
                    </CollapsibleContent>
                    <CollapsibleTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="mt-1 h-7 gap-1 text-xs text-muted-foreground hover:text-foreground self-start"
                      >
                        {isOpen ? (
                          <>
                            <ChevronDown className="h-3 w-3" />
                            Show less
                          </>
                        ) : (
                          <>
                            <ChevronRight className="h-3 w-3" />
                            Show {exampleRunIds.length - 3} more
                          </>
                        )}
                      </Button>
                    </CollapsibleTrigger>
                  </>
                )}
              </div>
            </Collapsible>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

function RunIdLink({ runId }: { runId: string }) {
  return (
    <a
      href={`/activity/runs?run_id=${runId}`}
      className={cn(
        "flex items-center gap-2 rounded-md px-3 py-2 text-xs font-mono",
        "border border-border bg-muted/40 hover:bg-muted transition-colors",
        "text-foreground hover:text-foreground group"
      )}
    >
      <span className="flex-1 truncate">{runId}</span>
      <ExternalLink className="h-3 w-3 text-muted-foreground group-hover:text-foreground shrink-0 transition-colors" />
    </a>
  );
}
