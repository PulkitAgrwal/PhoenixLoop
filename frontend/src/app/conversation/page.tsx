"use client";

import * as React from "react";

import { Eyebrow } from "@/components/ui/eyebrow";
import { ScenarioSelector } from "@/components/conversation/scenario-selector";
import { ChatInterface } from "@/components/conversation/chat-interface";
import { LiveTracePane } from "@/components/conversation/live-trace-pane";
import { AgentRun, SupportTicket } from "@/lib/types";

export default function ConversationPage() {
  const [selectedTicket, setSelectedTicket] = React.useState<SupportTicket | null>(null);
  const [isRunning, setIsRunning] = React.useState(false);
  const [lastRun, setLastRun] = React.useState<AgentRun | null>(null);

  return (
    <div className="mx-auto max-w-[1280px] px-5 py-10 lg:px-8 lg:py-14">
      <header className="flex flex-col gap-3">
        <Eyebrow tone="brand">Conversation</Eyebrow>
        <h1 className="text-display-lg text-ink-strong">
          Run a ticket. Watch every span land.
        </h1>
        <p className="max-w-[68ch] text-body-md text-body">
          Pick a scenario. The agent uses three tools (customer context, policy search,
          retrieve-similar-resolutions via Phoenix MCP) and one optional write
          (escalation). Every span is captured by Phoenix and rendered in the live trace
          pane on the right.
        </p>
      </header>

      <section
        className="mt-8 flex flex-col gap-3 rounded-md border border-hairline bg-canvas p-5"
        aria-label="Scenario"
      >
        <label
          htmlFor="scenario-select"
          className="text-eyebrow-mono uppercase text-mute"
        >
          Demo scenario
        </label>
        <ScenarioSelector
          onSelect={(ticket) => {
            setSelectedTicket(ticket);
            setIsRunning(false);
            setLastRun(null);
          }}
          disabled={isRunning}
        />
        <p className="text-body-sm text-mute">
          Each scenario maps to a row in the seeded SQLite. Live mode hits Gemini and Phoenix;
          set <code className="font-mono text-canvas-text-soft">LIGHTWEIGHT_DEMO=true</code> for fixture-only.
        </p>
      </section>

      <section
        className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_400px]"
        aria-label="Chat and live trace"
      >
        <div className="min-w-0">
          <ChatInterface
            ticket={selectedTicket}
            onRunStateChange={setIsRunning}
            onLastRunChange={setLastRun}
          />
        </div>
        <div className="min-w-0 h-[640px] lg:h-auto lg:min-h-[640px]">
          <LiveTracePane agentRun={lastRun} isRunning={isRunning} />
        </div>
      </section>
    </div>
  );
}
