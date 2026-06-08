"use client";

import * as React from "react";
import Link from "next/link";
import { motion, useInView, useReducedMotion } from "framer-motion";
import { ArrowRight, Check, Minus, X } from "lucide-react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Eyebrow } from "@/components/ui/eyebrow";
import { StatusDot } from "@/components/ui/status-dot";
import { CodeBlock } from "@/components/ui/code-block";
import { CodeInline } from "@/components/ui/code-inline";
import { HairlineDivider } from "@/components/ui/hairline-divider";
import { GridOverlay } from "@/components/ui/grid-overlay";
import { useHealingCycle } from "@/components/healing/healing-cycle-context";

// ────────────────────────────────────────────────────────────────────
// Hero
// ────────────────────────────────────────────────────────────────────

function WatchItHealButton() {
  const { startCycle, openModal, running, cycleId } = useHealingCycle();
  const hasActiveCycle = running || cycleId !== null;

  return (
    <Button
      variant="primary"
      size="lg"
      onClick={() => (hasActiveCycle ? openModal() : startCycle())}
    >
      {hasActiveCycle ? "Reopen healing cycle" : "Watch the agent heal itself (~5 min live · 90s fixture)"}
      <ArrowRight className="h-4 w-4" />
    </Button>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <GridOverlay variant="grid" fade="radial" />
      <div className="relative mx-auto grid max-w-[1280px] grid-cols-1 gap-12 px-5 pb-24 pt-16 lg:grid-cols-[1.05fr,1fr] lg:gap-16 lg:px-8 lg:pb-32 lg:pt-24">
        <div className="flex flex-col gap-7">
          <Eyebrow tone="brand" className="flex items-center gap-3">
            <StatusDot tone="brand" size="xs" pulse />
            <span>Arize · Phoenix · Gemini</span>
          </Eyebrow>
          <h1 className="text-[44px] leading-[1.05] tracking-tightish text-ink-strong sm:text-[52px] lg:text-display-xl">
            The agent that{" "}
            <span className="text-brand">watches itself</span> and{" "}
            <span className="text-brand">rewrites its own prompt</span>.
          </h1>
          <p className="max-w-[58ch] text-body-lg text-body">
            PhoenixLoop is a Gemini support agent that traces every run with Arize Phoenix,
            clusters its own failed evaluations, drafts a prompt fix from the failing spans,
            A/B-tests the candidate against a regression set, and gates promotion on the score.
            Self-improving, not theoretically — measurably.
          </p>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <WatchItHealButton />
            <Button asChild variant="outline" size="lg">
              <Link href="/conversation">Open the conversation</Link>
            </Button>
          </div>
          <div>
            <Link
              href="#architecture"
              className="text-body-sm text-mute underline-offset-4 hover:text-ink hover:underline"
            >
              Read the architecture ↘
            </Link>
          </div>

          <div className="pt-6 flex flex-wrap gap-5 text-body-sm text-mute">
            <span className="flex items-center gap-2">
              <StatusDot tone="brand" size="xs" /> <CodeInline>gemini-2.5-flash</CodeInline>
            </span>
            <span className="flex items-center gap-2">
              <StatusDot tone="brand" size="xs" /> <CodeInline>phoenix-mcp</CodeInline>
            </span>
            <span className="flex items-center gap-2">
              <StatusDot tone="brand" size="xs" /> <CodeInline>arize-phoenix-evals</CodeInline>
            </span>
          </div>
        </div>

        <HeroCodePanel />
      </div>
    </section>
  );
}

function HeroCodePanel() {
  return (
    <div className="relative flex flex-col gap-4">
      <CodeBlock
        filename="backend/src/tracing/instrumentor.py"
        language="python"
        copyValue={INSTRUMENTOR_CODE}
        showLineNumbers
      >
        {INSTRUMENTOR_CODE.split("\n").map((line, i) => (
          <span key={i}>
            {colorize(line)}
            {"\n"}
          </span>
        ))}
      </CodeBlock>
      <FauxTerminal />
    </div>
  );
}

const INSTRUMENTOR_CODE = `from phoenix.otel import register

tracer_provider = register(
    project_name="phoenixloop",
    endpoint="https://app.phoenix.arize.com/v1/traces",
    headers={"Authorization": f"Bearer {api_key}"},
    auto_instrument=True,
    batch=True,
)
# google-genai + ADK spans now stream to Phoenix.`;

function colorize(line: string): React.ReactNode {
  const keywords = ["from", "import", "return", "def", "class", "if", "else", "for", "with", "as"];
  // very light tokenizer for visual rhythm — not a real syntax highlighter
  const parts: React.ReactNode[] = [];
  const tokens = line.split(/(\b)/);
  let i = 0;
  for (const t of tokens) {
    if (keywords.includes(t.trim())) {
      parts.push(
        <span key={i++} className="text-brand-soft">
          {t}
        </span>
      );
    } else if (/^["'].*["']$/.test(t.trim()) || /f?"[^"]*"|f?'[^']*'/.test(t)) {
      parts.push(
        <span key={i++} className="text-warn/80">
          {t}
        </span>
      );
    } else if (/^#/.test(t.trim())) {
      parts.push(
        <span key={i++} className="text-mute">
          {t}
        </span>
      );
    } else {
      parts.push(<span key={i++}>{t}</span>);
    }
  }
  return parts;
}

type TerminalLine = {
  ts: string;
  ev: string;
  verb: string;
  arg: string;
  tone?: "fail";
};

function FauxTerminal() {
  const lines = React.useMemo<TerminalLine[]>(
    () => [
      { ts: "12:14:02.001", ev: "evaluator", verb: "CitationPresence", arg: "FAILED · score=0.42", tone: "fail" },
      { ts: "12:14:02.114", ev: "phoenix-mcp", verb: "get-spans", arg: "filter='eval.status=fail' limit=20" },
      { ts: "12:14:02.341", ev: "phoenix-mcp", verb: "get-span-annotations", arg: "span_id=7f1a…" },
      { ts: "12:14:02.602", ev: "diagnosis", verb: "cluster", arg: "failure_key=CitationPresence" },
      { ts: "12:14:02.918", ev: "proposal", verb: "patch", arg: "+1 line · cite [P-XXX]" },
      { ts: "12:14:03.244", ev: "experiment", verb: "run", arg: "n=5 baseline+candidate" },
      { ts: "12:14:04.001", ev: "release-gate", verb: "verdict", arg: "PROMOTED · 0.91 vs 0.42" },
    ],
    []
  );
  const [count, setCount] = React.useState(1);
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (mq.matches) {
      setCount(lines.length);
      return;
    }
    const id = setInterval(() => {
      setCount((c) => (c >= lines.length ? lines.length : c + 1));
    }, 900);
    return () => clearInterval(id);
  }, [lines.length]);

  return (
    <div className="rounded-md border border-hairline bg-canvas-soft overflow-hidden">
      <div className="flex items-center justify-between border-b border-hairline px-4 py-2">
        <div className="flex items-center gap-2 text-caption uppercase tracking-eyebrow text-mute">
          <StatusDot tone="brand" size="xs" pulse />
          live trace · stdout
        </div>
        <span className="font-mono text-caption text-mute">demo seed</span>
      </div>
      <div className="px-4 py-3 font-mono text-code text-canvas-text-soft min-h-[168px]">
        {lines.slice(0, count).map((l, i) => {
          if (l.tone === "fail") {
            return (
              <div key={i} className="animate-stream-line whitespace-nowrap text-fail">
                <span>{l.ts}</span>{" "}
                <span>{l.ev}</span>
                <span>:</span>
                <span>{l.verb}</span>
                <span>(</span>
                <span>{l.arg}</span>
                <span>)</span>
              </div>
            );
          }
          return (
            <div key={i} className="animate-stream-line whitespace-nowrap">
              <span className="text-mute">{l.ts}</span>{" "}
              <span className="text-brand">{l.ev}</span>
              <span className="text-mute">:</span>
              <span className="text-canvas-text-soft">{l.verb}</span>
              <span className="text-mute">(</span>
              <span className="text-body">{l.arg}</span>
              <span className="text-mute">)</span>
            </div>
          );
        })}
        {count < lines.length && (
          <span className="inline-block h-3.5 w-1.5 translate-y-0.5 bg-brand animate-pulse-dot" />
        )}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Stats strip
// ────────────────────────────────────────────────────────────────────

type Stats = {
  agent_runs_traced: number;
  evaluators_wired: number;
  mcp_tool_calls_per_run_avg: number;
  prompts_auto_promoted: number;
};

function StatsStrip() {
  const [stats, setStats] = React.useState<Stats | null>(null);
  const [loaded, setLoaded] = React.useState(false);
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      const res = await api.stats.get().catch(() => null);
      if (!cancelled && res?.ok && res.data) {
        setStats(res.data as Stats);
      }
      if (!cancelled) setLoaded(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const cells = [
    { label: "Agent runs traced", value: stats?.agent_runs_traced ?? "—", suffix: "in Phoenix" },
    { label: "Evaluators wired", value: stats?.evaluators_wired ?? "—", suffix: "code · LLM · MCP" },
    {
      label: "MCP tool calls / run",
      value: stats ? stats.mcp_tool_calls_per_run_avg.toFixed(2) : "—",
      suffix: "avg recent 50",
    },
    { label: "Prompts auto-promoted", value: stats?.prompts_auto_promoted ?? "—", suffix: "release-gate" },
  ];

  return (
    <section className="border-y border-hairline bg-canvas">
      <div className="mx-auto max-w-[1280px] grid grid-cols-2 lg:grid-cols-4 px-5 lg:px-8">
        {cells.map((c, i) => (
          <div
            key={c.label}
            className={
              "px-4 py-6 lg:py-8 " +
              (i > 0 ? "lg:border-l border-hairline " : "") +
              (i === 2 ? "lg:border-l border-hairline " : "") +
              (i % 2 === 1 ? "border-l border-hairline " : "")
            }
          >
            <div
              className={
                "num-mono text-[34px] leading-[40px] " +
                (loaded ? "text-ink-strong" : "text-mute")
              }
            >
              {c.value}
            </div>
            <div className="mt-2 flex items-center justify-between gap-3">
              <span className="text-body-sm text-body">{c.label}</span>
              <span className="text-caption uppercase tracking-eyebrow text-mute">{c.suffix}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// ────────────────────────────────────────────────────────────────────
// The loop — 7 nodes
// ────────────────────────────────────────────────────────────────────

const LOOP_NODES = [
  { n: "01", title: "Observe", body: "Every agent turn, tool call, and judge call streams to Phoenix as OTel spans.", tag: "phoenix.otel.register" },
  { n: "02", title: "Evaluate", body: "7 code evals + 4 LLM judges (2 Phoenix Evals templates + 2 custom) + 3 Phoenix tool evals score every run.", tag: "arize-phoenix-evals" },
  { n: "03", title: "Cluster", body: "Repeat failures group by deterministic failure_key. Three strikes trips an improvement trigger.", tag: "failure_aggregator" },
  { n: "04", title: "Diagnose", body: "A sub-agent reads its own failing spans via Phoenix MCP — get-spans, get-span-annotations — and names the pattern.", tag: "phoenix-mcp:get-spans" },
  { n: "05", title: "Patch prompt", body: "Gemini drafts a minimal one-line addition to the system prompt. The diff is human-readable.", tag: "patch_synthesis" },
  { n: "06", title: "Experiment", body: "Baseline-vs-candidate on 5 frozen regression examples. Code-evals only, no judge round-trips.", tag: "experiment.run" },
  { n: "07", title: "Gate", body: "Release-gate verdict from the score delta. Promotion is automatic above threshold, human in-the-loop below.", tag: "release_gate" },
];

function LoopSection() {
  const reduceMotion = useReducedMotion();
  const listRef = React.useRef<HTMLOListElement | null>(null);
  const inView = useInView(listRef, { amount: 0.35, once: false });
  const [activeIndex, setActiveIndex] = React.useState(0);

  React.useEffect(() => {
    if (reduceMotion) return;
    if (!inView) return;
    const id = window.setInterval(() => {
      setActiveIndex((i) => (i + 1) % LOOP_NODES.length);
    }, 600);
    return () => window.clearInterval(id);
  }, [inView, reduceMotion]);

  return (
    <section className="relative">
      <div className="mx-auto max-w-[1280px] px-5 py-20 lg:px-8 lg:py-28">
        <SectionHeader
          eyebrow="The loop"
          title="Seven stages. One closed circuit."
          body="An LLM agent without a loop is a sample. With this loop, every failure becomes a labeled example, every cluster becomes a prompt patch, every patch becomes a measurable experiment."
        />
        <ol
          ref={listRef}
          className="mt-12 grid grid-cols-1 gap-px overflow-hidden rounded-md border border-hairline bg-hairline md:grid-cols-2 lg:grid-cols-[repeat(7,minmax(0,1fr))]"
        >
          {LOOP_NODES.map((node, i) => {
            const isActive = !reduceMotion && inView && i === activeIndex;
            return (
              <motion.li
                key={node.n}
                initial={reduceMotion ? false : { opacity: 0, x: -16 }}
                whileInView={reduceMotion ? undefined : { opacity: 1, x: 0 }}
                viewport={{ once: true, amount: 0.3 }}
                transition={
                  reduceMotion
                    ? undefined
                    : { duration: 0.35, delay: i * 0.08, ease: "easeOut" }
                }
                className="relative flex h-full flex-col gap-3 bg-canvas p-5 transition-colors hover:bg-canvas-soft"
              >
                <div className="flex items-center justify-between">
                  <span className="num-mono text-caption text-mute">{node.n}</span>
                  {i < LOOP_NODES.length - 1 && (
                    <ArrowRight className="h-3.5 w-3.5 text-mute hidden lg:block" aria-hidden />
                  )}
                </div>
                <h3 className="text-body-md-strong text-ink-strong">{node.title}</h3>
                <p className="text-body-sm text-body">{node.body}</p>
                <CodeInline className="self-start mt-auto">{node.tag}</CodeInline>
                {isActive && (
                  <motion.span
                    aria-hidden
                    layoutId="loop-active-pulse"
                    className="pointer-events-none absolute inset-0 rounded-md ring-2 ring-brand/60"
                    transition={{ duration: 0.3, ease: "easeOut" }}
                  />
                )}
              </motion.li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}

// ────────────────────────────────────────────────────────────────────
// Three-column evidence row
// ────────────────────────────────────────────────────────────────────

function EvidenceRow() {
  return (
    <section className="border-t border-hairline">
      <div className="mx-auto max-w-[1280px] px-5 py-20 lg:px-8 lg:py-24">
        <SectionHeader
          eyebrow="Receipts, not claims"
          title="Three pieces of evidence."
          body="If the agent says it observes itself, the spans should be visible. If it says it evaluates itself, the evaluators should be named. If it says it improves itself, the before-and-after should be auditable."
        />
        <div className="mt-12 grid gap-6 lg:grid-cols-3">
          <EvidenceCard
            number="01"
            title="Real Phoenix spans"
            subtitle="not a console logger"
            lines={[
              "ADK · agent_run",
              "phoenix-mcp:get-spans",
              "phoenix-mcp:get-span-annotations",
              "phoenix-mcp:get-dataset-examples",
              "google-genai · judges_combined",
              "google-genai · patch_synthesis",
            ]}
            footer="Visible in Arize Phoenix, deep-linked from every run."
          />
          <EvidenceCard
            number="02"
            title="Real evaluators"
            subtitle="14 wired, named, deterministic"
            lines={[
              "code · CitationPresence",
              "code · RefundGuard",
              "code · ToolSequence",
              "judge · Hallucination (Phoenix Evals)",
              "judge · QA-Correctness (Phoenix Evals)",
              "judge · PolicyCompliance (custom)",
            ]}
            footer="Code-evals + Phoenix Evals templates + custom judges."
          />
          <EvidenceCard
            number="03"
            title="Real before/after"
            subtitle="0.42 → 0.91 on one cluster"
            lines={[
              "Baseline prompt v1.1",
              "→ Candidate prompt v1.2",
              "Resolution correctness · 0.42 → 0.91",
              "Citation presence · 0.10 → 0.98",
              "Regression canaries · 5/5 pass",
              "Verdict · PROMOTED",
            ]}
            footer="Code-evals only in the experiment hot path."
          />
        </div>
      </div>
    </section>
  );
}

function EvidenceCard({
  number,
  title,
  subtitle,
  lines,
  footer,
}: {
  number: string;
  title: string;
  subtitle: string;
  lines: string[];
  footer: string;
}) {
  return (
    <div className="rounded-md border border-hairline bg-canvas p-6">
      <div className="flex items-center gap-3">
        <span className="num-mono text-caption text-mute">{number}</span>
        <Eyebrow tone="mute">{subtitle}</Eyebrow>
      </div>
      <h3 className="mt-2 text-display-sm text-ink-strong">{title}</h3>
      <ul className="mt-5 flex flex-col gap-1.5 font-mono text-code">
        {lines.map((l) => (
          <li key={l} className="flex items-baseline gap-2 text-canvas-text-soft">
            <span className="text-brand">›</span>
            <span>{l}</span>
          </li>
        ))}
      </ul>
      <HairlineDivider className="my-5" />
      <p className="text-body-sm text-body">{footer}</p>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Architecture diagram (hand-built SVG)
// ────────────────────────────────────────────────────────────────────

function ArchitectureDiagram() {
  return (
    <section id="architecture" className="border-t border-hairline">
      <div className="mx-auto max-w-[1280px] px-5 py-20 lg:px-8 lg:py-24">
        <SectionHeader
          eyebrow="Architecture"
          title="One agent. Three feedback paths."
          body="The support agent calls Phoenix MCP at runtime to retrieve few-shot exemplars from a curated dataset of resolved tickets. Failed runs aggregate. A separate diagnosis sub-agent reads the failing spans back from Phoenix MCP, names the root cause, and proposes a patch. Experiments score before-and-after on the same dataset."
        />
        <div className="mt-12 overflow-x-auto">
          <svg
            viewBox="0 0 1180 480"
            className="w-full min-w-[920px]"
            role="img"
            aria-label="PhoenixLoop architecture: support agent, Phoenix MCP, diagnosis sub-agent, experiment runner"
          >
            <defs>
              <marker
                id="arrowhead"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#3d3a39" />
              </marker>
              <marker
                id="arrowhead-brand"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#00d992" />
              </marker>
            </defs>

            {/* Top row */}
            <ArchBox x={40} y={40} w={220} h={80} label="Customer ticket" sub="REST /api/tickets" />
            <ArchBox x={320} y={40} w={260} h={80} label="Support agent · ADK" sub="gemini-2.5-flash · 3 tools" emphasis />
            <ArchBox x={640} y={40} w={260} h={80} label="Phoenix · OTel + Evals" sub="auto_instrument · batch" />
            <ArchBox x={960} y={40} w={180} h={80} label="Response" sub="cited · structured" />

            {/* Middle row — MCP path */}
            <ArchBox x={320} y={200} w={260} h={80} label="Phoenix MCP" sub="get-dataset-examples · get-spans" brand />
            <ArchBox x={640} y={200} w={260} h={80} label="Diagnosis sub-agent" sub="reads its own failing spans" emphasis />

            {/* Bottom row */}
            <ArchBox x={40} y={360} w={220} h={80} label="Failure aggregator" sub="failure_key · 3-strike rule" />
            <ArchBox x={320} y={360} w={260} h={80} label="Patch synthesis" sub="one-line prompt diff" />
            <ArchBox x={640} y={360} w={260} h={80} label="Experiment runner" sub="baseline vs candidate · 5 ex" />
            <ArchBox x={960} y={360} w={180} h={80} label="Release gate" sub="PROMOTED / REJECT" />

            {/* Arrows top row */}
            <ArchArrow x1={260} y1={80} x2={320} y2={80} />
            <ArchArrow x1={580} y1={80} x2={640} y2={80} />
            <ArchArrow x1={900} y1={80} x2={960} y2={80} />

            {/* Agent → MCP (brand: this is the runtime MCP call) */}
            <ArchArrow x1={450} y1={120} x2={450} y2={200} brand />
            <text x={465} y={170} className="font-mono" fill="#2fd6a1" fontSize="12">
              retrieve_similar_resolutions
            </text>

            {/* Phoenix → diagnosis (failures flow) */}
            <ArchArrow x1={770} y1={120} x2={770} y2={200} />
            <text x={785} y={170} className="font-mono" fill="#bdbdbd" fontSize="12">
              failing spans
            </text>

            {/* Diagnosis → MCP (brand) */}
            <ArchArrow x1={640} y1={240} x2={580} y2={240} brand />

            {/* Aggregator → patch */}
            <ArchArrow x1={260} y1={400} x2={320} y2={400} />
            <ArchArrow x1={580} y1={400} x2={640} y2={400} />
            <ArchArrow x1={900} y1={400} x2={960} y2={400} brand />

            {/* Diagnosis → patch */}
            <ArchArrow x1={770} y1={280} x2={450} y2={360} />

            {/* Phoenix → aggregator (eval results) */}
            <ArchArrow x1={770} y1={120} x2={150} y2={360} dashed />
          </svg>
        </div>
      </div>
    </section>
  );
}

function ArchBox({
  x,
  y,
  w,
  h,
  label,
  sub,
  emphasis,
  brand,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  sub: string;
  emphasis?: boolean;
  brand?: boolean;
}) {
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={8}
        fill="#101010"
        stroke={brand ? "#00d992" : "#3d3a39"}
        strokeWidth={emphasis ? 2 : 1}
      />
      <text x={x + 16} y={y + 32} fill={brand ? "#2fd6a1" : "#f2f2f2"} fontSize="15" fontWeight={600}>
        {label}
      </text>
      <text x={x + 16} y={y + 56} fill="#8b949e" fontSize="12" className="font-mono">
        {sub}
      </text>
    </g>
  );
}

function ArchArrow({
  x1,
  y1,
  x2,
  y2,
  brand,
  dashed,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  brand?: boolean;
  dashed?: boolean;
}) {
  return (
    <line
      x1={x1}
      y1={y1}
      x2={x2}
      y2={y2}
      stroke={brand ? "#00d992" : "#3d3a39"}
      strokeWidth={1.5}
      strokeDasharray={dashed ? "4 4" : undefined}
      markerEnd={`url(#${brand ? "arrowhead-brand" : "arrowhead"})`}
    />
  );
}

// ────────────────────────────────────────────────────────────────────
// Code walks (three)
// ────────────────────────────────────────────────────────────────────

function CodeWalks() {
  return (
    <section className="border-t border-hairline">
      <div className="mx-auto max-w-[1280px] px-5 py-20 lg:px-8 lg:py-24">
        <SectionHeader
          eyebrow="Code walks"
          title="Three pieces of code that carry the claim."
          body="The most reassuring thing on a marketing page is the actual production code."
        />
        <div className="mt-12 flex flex-col gap-12">
          <CodeWalk
            number="01"
            title="Trace every Gemini call with one register()"
            body={
              <>
                Replaces our hand-rolled OTel setup with the canonical Phoenix call. The{" "}
                <CodeInline>auto_instrument=True</CodeInline> flag picks up both ADK agent spans and
                direct google-genai calls — so the LLM judges are no longer invisible.
              </>
            }
            code={INSTRUMENTOR_CODE}
            filename="backend/src/tracing/instrumentor.py"
          />
          <CodeWalk
            number="02"
            title="Few-shot retrieval from a Phoenix dataset"
            body={
              <>
                The support agent calls this tool before drafting any non-trivial response. Top-3
                exemplars come back from the <CodeInline>successful-resolutions</CodeInline> dataset
                in Phoenix Cloud via MCP. The retrieval span is visible in every trace.
              </>
            }
            code={`@retry(max_attempts=3, retryable_exceptions=(httpx.TimeoutException,))
async def retrieve_similar_resolutions(
    category: str,
    brief: str,
) -> list[ResolutionExample]:
    """Top-3 exemplars from the Phoenix \`successful-resolutions\` dataset."""
    examples = await phoenix_client.get_dataset_examples(
        dataset="successful-resolutions",
        filter={"category": category},
        limit=3,
    )
    return [ResolutionExample.model_validate(e) for e in examples]`}
            filename="backend/src/agent/tools.py"
          />
          <CodeWalk
            number="03"
            title="Diagnosis sub-agent reads its own failing spans"
            body={
              <>
                The diagnosis agent uses the Phoenix MCP toolset as its tool surface. The Live Trace
                pane shows <CodeInline>phoenix-mcp:get-spans</CodeInline> and{" "}
                <CodeInline>phoenix-mcp:get-span-annotations</CodeInline> spans every time it runs —
                real observability data flowing back into reasoning.
              </>
            }
            code={`diagnosis_agent = Agent(
    name="diagnosis",
    model=settings.gemini_model,                  # flash
    tools=[mcp_toolset],                          # phoenix-mcp
    generate_content_config=GenerateContentConfig(
        thinking_config=ThinkingConfig(thinking_budget=128),
    ),
    instruction=DIAGNOSIS_PROMPT,                 # JSON-only output, ≤2 MCP calls
)
result = await Runner(agent=diagnosis_agent, ...).run_async(failure_key)`}
            filename="backend/src/agent/diagnosis_agent.py"
          />
        </div>
      </div>
    </section>
  );
}

function CodeWalk({
  number,
  title,
  body,
  code,
  filename,
}: {
  number: string;
  title: string;
  body: React.ReactNode;
  code: string;
  filename: string;
}) {
  return (
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1fr,1.4fr]">
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <span className="num-mono text-caption text-mute">{number}</span>
          <Eyebrow tone="brand">Code walk</Eyebrow>
        </div>
        <h3 className="text-display-md text-ink-strong">{title}</h3>
        <p className="text-body-md text-body">{body}</p>
      </div>
      <CodeBlock filename={filename} language="python" copyValue={code} showLineNumbers>
        {code.split("\n").map((line, i) => (
          <span key={i}>
            {colorize(line)}
            {"\n"}
          </span>
        ))}
      </CodeBlock>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Comparison table
// ────────────────────────────────────────────────────────────────────

const COMPARE_ROWS: { col: string; phoenixloop: string; common: string }[] = [
  { col: "Tracing", phoenixloop: "phoenix.otel.register · batched · auto-instrument", common: "Print-to-stdout / custom JSON logs" },
  { col: "MCP usage", phoenixloop: "Real Phoenix MCP at runtime (sub-agent + RAG)", common: "Hand-rolled HTTP call to /api/spans" },
  { col: "Evaluation", phoenixloop: "7 code · 4 judges (2 Phoenix Evals) · 3 tool", common: "One ‘LLM-as-judge’ score, no breakdown" },
  { col: "Improvement loop", phoenixloop: "Diagnosis sub-agent reads failing spans · patches prompt", common: "Manual prompt edits in a Notion doc" },
  { col: "Promotion", phoenixloop: "Score-gated baseline-vs-candidate experiment", common: "Vibes; ship it and watch metrics" },
  { col: "Model choice", phoenixloop: "Flash everywhere · thinking_budget tuned per agent", common: "Pro for everything · billed accordingly" },
];

function CompareTable() {
  return (
    <section className="border-t border-hairline">
      <div className="mx-auto max-w-[1280px] px-5 py-20 lg:px-8 lg:py-24">
        <SectionHeader
          eyebrow="What it is. What it isn’t."
          title="A dense difference, not a vibe."
          body="Most agent demos describe what the agent should do. This row says what the architecture actually does — and what the common alternative looks like."
        />
        <div className="mt-12 overflow-hidden rounded-md border border-hairline">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-canvas-soft text-caption uppercase tracking-eyebrow text-mute">
                <th className="px-5 py-3 font-semibold w-[18%]">Surface</th>
                <th className="px-5 py-3 font-semibold w-[42%]">
                  <span className="text-brand">PhoenixLoop</span>
                </th>
                <th className="px-5 py-3 font-semibold w-[40%]">Common alternative</th>
              </tr>
            </thead>
            <tbody>
              {COMPARE_ROWS.map((r, i) => (
                <tr
                  key={r.col}
                  className={
                    "border-t border-hairline " + (i % 2 === 0 ? "bg-canvas" : "bg-canvas/60")
                  }
                >
                  <td className="px-5 py-4 align-top text-body-md-strong text-ink-strong">{r.col}</td>
                  <td className="px-5 py-4 align-top text-body-sm text-ink">
                    <span className="inline-flex items-start gap-2">
                      <Check className="mt-1 h-3.5 w-3.5 shrink-0 text-brand" aria-hidden />
                      <span>{r.phoenixloop}</span>
                    </span>
                  </td>
                  <td className="px-5 py-4 align-top text-body-sm text-mute">
                    <span className="inline-flex items-start gap-2">
                      <Minus className="mt-1 h-3.5 w-3.5 shrink-0 text-mute" aria-hidden />
                      <span>{r.common}</span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

// ────────────────────────────────────────────────────────────────────
// Anti-claim block — what we did NOT build
// ────────────────────────────────────────────────────────────────────

function AntiClaim() {
  const lines = [
    "A glassmorphic ‘AI gradient’ landing page.",
    "A fake terminal that types Lorem-ipsum forever.",
    "A LangSmith-tier observability rewrite.",
    "An evals framework competing with Phoenix.",
    "Agents that A2A-call ten dummy agents to look busy.",
  ];
  return (
    <section className="border-t border-hairline bg-canvas-soft/50">
      <div className="mx-auto max-w-[1280px] grid grid-cols-1 gap-10 px-5 py-16 lg:grid-cols-[1fr,1.4fr] lg:px-8 lg:py-20">
        <div>
          <Eyebrow tone="mute">Anti-claim</Eyebrow>
          <h3 className="mt-3 text-display-md text-ink-strong">
            Things we deliberately did <span className="text-fail">not</span> build.
          </h3>
          <p className="mt-4 text-body-md text-body max-w-[42ch]">
            A short list is a credibility signal. Anyone can claim a self-improving agent. Below is
            the surface area we said no to.
          </p>
        </div>
        <ul className="flex flex-col gap-3">
          {lines.map((l) => (
            <li
              key={l}
              className="flex items-start gap-3 rounded-md border border-hairline bg-canvas p-4"
            >
              <X className="mt-1 h-3.5 w-3.5 shrink-0 text-fail" aria-hidden />
              <span className="text-body-md text-ink">{l}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// ────────────────────────────────────────────────────────────────────
// CTA band + footer
// ────────────────────────────────────────────────────────────────────

function CTABand() {
  return (
    <section className="border-y-2 border-brand">
      <div className="mx-auto flex max-w-[1280px] flex-col gap-6 px-5 py-16 lg:flex-row lg:items-center lg:justify-between lg:px-8 lg:py-20">
        <div className="max-w-[60ch]">
          <Eyebrow tone="brand">Run it locally</Eyebrow>
          <h3 className="mt-3 text-display-md text-ink-strong">
            Boot the stack. Click one ticket. Watch one promotion.
          </h3>
          <p className="mt-3 text-body-md text-body">
            The seed runs six tickets, two intentional failures, one diagnosis, one experiment and
            one release-gate verdict. Around 4–5 minutes in live mode (real Gemini calls) or ~90s
            with <code>LIGHTWEIGHT_DEMO=true</code> (fixture replay).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button asChild variant="primary" size="lg">
            <Link href="/conversation">
              Open conversation <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="/healing/improvements">See a live healing trace</Link>
          </Button>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="bg-canvas">
      <div className="mx-auto flex max-w-[1280px] flex-col gap-8 px-5 py-12 lg:flex-row lg:items-end lg:justify-between lg:px-8">
        <div className="flex flex-col gap-3 max-w-[40ch]">
          <div className="flex items-center gap-2">
            <span className="relative inline-flex h-5 w-5 items-center justify-center">
              <span className="absolute inset-0 rounded-sm border border-brand/40" />
              <span className="absolute inset-[2.5px] rounded-[2px] bg-brand" />
            </span>
            <span className="text-body-md-strong text-ink-strong">PhoenixLoop</span>
          </div>
          <p className="text-body-sm text-mute">
            Hackathon submission for the Arize self-improvement track. Built on Gemini, ADK, Arize
            Phoenix, and the Phoenix MCP server.
          </p>
        </div>
        <nav className="grid grid-cols-2 gap-x-12 gap-y-1 text-body-sm" aria-label="Footer">
          <Link href="/conversation" className="text-body hover:text-ink">
            Conversation
          </Link>
          <Link href="/activity/runs" className="text-body hover:text-ink">
            Activity
          </Link>
          <Link href="/healing/improvements" className="text-body hover:text-ink">
            Improvements
          </Link>
          <Link href="/healing/experiments" className="text-body hover:text-ink">
            A/B prompt tests
          </Link>
          <Link href="/prompts" className="text-body hover:text-ink">
            Prompts
          </Link>
          <Link href="/settings" className="text-body hover:text-ink">
            Settings
          </Link>
        </nav>
      </div>
      <div className="border-t border-hairline">
        <div className="mx-auto flex max-w-[1280px] items-center justify-between px-5 py-4 lg:px-8">
          <span className="text-caption text-mute">PhoenixLoop · local dev build</span>
          <span className="font-mono text-caption text-mute">PhoenixLoop · v0.1.0</span>
        </div>
      </div>
    </footer>
  );
}

// ────────────────────────────────────────────────────────────────────
// Section header helper
// ────────────────────────────────────────────────────────────────────

function SectionHeader({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr,1.4fr] lg:gap-12">
      <div>
        <Eyebrow tone="mute">{eyebrow}</Eyebrow>
        <h2 className="mt-3 text-display-lg text-ink-strong">{title}</h2>
      </div>
      <p className="text-body-md text-body lg:pt-12">{body}</p>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────

export default function LandingPage() {
  return (
    <>
      <Hero />
      <StatsStrip />
      <LoopSection />
      <EvidenceRow />
      <ArchitectureDiagram />
      <CodeWalks />
      <CompareTable />
      <AntiClaim />
      <CTABand />
      <Footer />
    </>
  );
}
