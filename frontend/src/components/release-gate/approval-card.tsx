"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle, XCircle, Clock, Loader2, ShieldX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import { ReleaseDecision } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ApprovalCardProps {
  decisionId: string;
  decision: ReleaseDecision;
  onApprove: () => void;
  onReject: () => void;
  decidedAt?: string;
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function ApprovalCard({
  decisionId,
  decision,
  onApprove,
  onReject,
  decidedAt,
}: ApprovalCardProps) {
  const [reviewerId, setReviewerId] = useState("demo-reviewer");
  const [comment, setComment] = useState("");
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const handleApprove = async () => {
    setActionError(null);
    setApproving(true);
    try {
      const res = await api.releaseGate.approve(decisionId, reviewerId, comment);
      if (!res.ok) {
        setActionError(res.error ?? "Approval failed. Please try again.");
      } else {
        onApprove();
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Unexpected error");
    } finally {
      setApproving(false);
    }
  };

  const handleReject = async () => {
    setActionError(null);
    setRejecting(true);
    try {
      const res = await api.releaseGate.reject(decisionId, reviewerId, comment);
      if (!res.ok) {
        setActionError(res.error ?? "Rejection failed. Please try again.");
      } else {
        onReject();
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Unexpected error");
    } finally {
      setRejecting(false);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">Human Review</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <AnimatePresence mode="wait">
          {/* ── Pending human review ── */}
          {decision === "pending_human_review" && (
            <motion.div
              key="pending"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
              className="space-y-4"
            >
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-amber-500" />
                <span className="text-sm text-amber-700 dark:text-amber-400 font-medium">
                  Awaiting human approval
                </span>
              </div>

              <Separator />

              <div className="space-y-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Reviewer ID
                  </label>
                  <Input
                    value={reviewerId}
                    onChange={(e) => setReviewerId(e.target.value)}
                    placeholder="reviewer-id"
                    className="h-8 text-sm"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Comment (optional)
                  </label>
                  <Textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="Add a comment about this decision..."
                    className="min-h-[72px] resize-none text-sm"
                  />
                </div>
              </div>

              {/* Error */}
              <AnimatePresence>
                {actionError && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-400"
                  >
                    <XCircle className="h-3.5 w-3.5 shrink-0" />
                    {actionError}
                  </motion.div>
                )}
              </AnimatePresence>

              <div className="flex gap-2">
                <Button
                  size="sm"
                  className={cn(
                    "flex-1 gap-2",
                    "bg-green-600 hover:bg-green-700 text-white dark:bg-green-600 dark:hover:bg-green-700"
                  )}
                  onClick={handleApprove}
                  disabled={approving || rejecting || !reviewerId.trim()}
                >
                  {approving ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <CheckCircle className="h-3.5 w-3.5" />
                  )}
                  {approving ? "Approving…" : "Approve"}
                </Button>

                <Button
                  size="sm"
                  variant="outline"
                  className={cn(
                    "flex-1 gap-2",
                    "border-red-300 text-red-700 hover:bg-red-50 hover:border-red-400",
                    "dark:border-red-700 dark:text-red-400 dark:hover:bg-red-950/40"
                  )}
                  onClick={handleReject}
                  disabled={approving || rejecting || !reviewerId.trim()}
                >
                  {rejecting ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5" />
                  )}
                  {rejecting ? "Rejecting…" : "Reject"}
                </Button>
              </div>
            </motion.div>
          )}

          {/* ── Promoted / Approved ── */}
          {decision === "promoted" && (
            <motion.div
              key="promoted"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.3, ease: "backOut" }}
              className="space-y-3"
            >
              <div className="flex items-center gap-3">
                <motion.div
                  initial={{ scale: 0, rotate: -180 }}
                  animate={{ scale: 1, rotate: 0 }}
                  transition={{ type: "spring", stiffness: 300, damping: 20, delay: 0.1 }}
                >
                  <CheckCircle className="h-8 w-8 text-green-600 dark:text-green-400" />
                </motion.div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-green-700 dark:text-green-300">
                      Approved
                    </span>
                    <Badge className="bg-green-100 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-400 dark:border-green-800 text-xs">
                      Promoted
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Candidate tagged as production
                  </p>
                </div>
              </div>
              {decidedAt && (
                <p className="text-xs text-muted-foreground">
                  Decided at: {formatDateTime(decidedAt)}
                </p>
              )}
            </motion.div>
          )}

          {/* ── Rejected ── */}
          {decision === "rejected" && (
            <motion.div
              key="rejected"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.3, ease: "backOut" }}
              className="space-y-3"
            >
              <div className="flex items-center gap-3">
                <motion.div
                  initial={{ scale: 0, rotate: 180 }}
                  animate={{ scale: 1, rotate: 0 }}
                  transition={{ type: "spring", stiffness: 300, damping: 20, delay: 0.1 }}
                >
                  <XCircle className="h-8 w-8 text-red-600 dark:text-red-400" />
                </motion.div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-red-700 dark:text-red-300">
                      Rejected
                    </span>
                    <Badge className="bg-red-100 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-400 dark:border-red-800 text-xs">
                      Not Promoted
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Candidate did not meet promotion criteria
                  </p>
                </div>
              </div>
              {decidedAt && (
                <p className="text-xs text-muted-foreground">
                  Decided at: {formatDateTime(decidedAt)}
                </p>
              )}
            </motion.div>
          )}

          {/* ── Blocked critical failure ── */}
          {decision === "blocked_critical_failure" && (
            <motion.div
              key="blocked"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.3, ease: "backOut" }}
              className="space-y-3"
            >
              <div className="flex items-center gap-3">
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: "spring", stiffness: 300, damping: 20, delay: 0.1 }}
                >
                  <ShieldX className="h-8 w-8 text-red-700 dark:text-red-400" />
                </motion.div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-red-800 dark:text-red-300">
                      Blocked
                    </span>
                    <Badge className="bg-red-200 text-red-800 border-red-300 dark:bg-red-950 dark:text-red-400 dark:border-red-800 text-xs">
                      Critical Failure
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Automatically blocked due to critical failure detected
                  </p>
                </div>
              </div>
              {decidedAt && (
                <p className="text-xs text-muted-foreground">
                  Decided at: {formatDateTime(decidedAt)}
                </p>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </CardContent>
    </Card>
  );
}
