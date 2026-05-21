"use client";

import React, { useState } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { ScenarioSelector } from "@/components/conversation/scenario-selector";
import { ChatInterface } from "@/components/conversation/chat-interface";
import { SupportTicket } from "@/lib/types";

export default function ConversationPage() {
  const [selectedTicket, setSelectedTicket] = useState<SupportTicket | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Support Conversation"
        description="Run the agent on a support ticket and observe live tool calls, traces, and evaluations."
      />

      {/* Scenario selector */}
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground">
          Demo Scenario
        </label>
        <ScenarioSelector
          onSelect={(ticket) => {
            setSelectedTicket(ticket);
            setIsRunning(false);
          }}
          disabled={isRunning}
        />
        <p className="text-xs text-muted-foreground">
          Select a support ticket to load it into the chat and run the PhoenixLoop
          agent against it.
        </p>
      </div>

      {/* Chat interface */}
      <ChatInterface ticket={selectedTicket} />
    </div>
  );
}
