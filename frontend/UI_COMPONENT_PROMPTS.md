# PhoenixLoop — UI Component Patterns Reference

**Stack:** Next.js 14 (App Router) · shadcn/ui · Tailwind CSS (slate theme) · Framer Motion 11 · Recharts 2.12 · Lucide React

> Copy-pasteable animation snippets and component compositions for each of the 8 dashboard pages.
> All imports use `motion/react` (Framer Motion 11+). Every snippet is typed and production-ready.

---

## Table of Contents

1. [Shared / Layout Patterns](#1-shared--layout-patterns)
2. [Demo Home](#2-demo-home-pagetsx)
3. [Support Conversation](#3-support-conversation)
4. [Trace & Eval View](#4-trace--eval-view)
5. [Failure Trends](#5-failure-trends)
6. [Improvement Proposal](#6-improvement-proposal)
7. [Experiment Results](#7-experiment-results)
8. [Release Gate](#8-release-gate)

---

## 1. Shared / Layout Patterns

### 1.1 Sidebar Navigation with Active State Animation

**shadcn/ui components:** `Separator`, `Tooltip`, `TooltipProvider`, `TooltipContent`, `TooltipTrigger`

```tsx
// components/sidebar.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import {
  Home, MessageSquare, Activity, TrendingDown,
  Lightbulb, FlaskConical, ShieldCheck, Settings
} from "lucide-react";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/",               icon: Home,          label: "Demo Home" },
  { href: "/conversation",   icon: MessageSquare, label: "Conversation" },
  { href: "/traces",         icon: Activity,      label: "Trace & Eval" },
  { href: "/failures",       icon: TrendingDown,  label: "Failure Trends" },
  { href: "/improvements",   icon: Lightbulb,     label: "Improvement" },
  { href: "/experiments",    icon: FlaskConical,  label: "Experiments" },
  { href: "/release-gate",   icon: ShieldCheck,   label: "Release Gate" },
  { href: "/settings",       icon: Settings,      label: "Settings" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-56 flex-col border-r border-slate-200 bg-white px-3 py-4">
      {/* Logo */}
      <div className="mb-4 flex items-center gap-2 px-2">
        <div className="h-7 w-7 rounded-md bg-orange-500" />
        <span className="text-sm font-semibold text-slate-900">PhoenixLoop</span>
      </div>

      <Separator className="mb-3" />

      <nav className="flex flex-1 flex-col gap-1">
        {navItems.map(({ href, icon: Icon, label }) => {
          const isActive = pathname === href;
          return (
            <Link key={href} href={href} className="relative">
              {/* Active background pill — layout-animated */}
              {isActive && (
                <motion.div
                  layoutId="sidebar-active-pill"
                  className="absolute inset-0 rounded-md bg-slate-100"
                  transition={{ type: "spring", stiffness: 400, damping: 35 }}
                />
              )}
              <span
                className={cn(
                  "relative flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "text-slate-900"
                    : "text-slate-500 hover:text-slate-800"
                )}
              >
                <Icon size={16} />
                {label}
              </span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
```

---

### 1.2 Page Transition Animations

**Pattern:** Wrap each page's root element in a `motion.div` with `AnimatePresence` in the layout.

```tsx
// app/layout.tsx
import { AnimatePresence } from "motion/react";

// In the root layout, pass `pathname` as key to AnimatePresence children.
// Since RSC can't use hooks, create a client wrapper:

// components/page-transition.tsx
"use client";
import { motion } from "motion/react";

const pageVariants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit:    { opacity: 0, y: -4 },
};

const pageTransition = { duration: 0.18, ease: [0.25, 0.1, 0.25, 1.0] };

export function PageTransition({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      variants={pageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={pageTransition}
      className="flex-1 overflow-y-auto p-6"
    >
      {children}
    </motion.div>
  );
}
```

Usage in each page:
```tsx
// app/failures/page.tsx
import { PageTransition } from "@/components/page-transition";

export default function FailuresPage() {
  return (
    <PageTransition>
      {/* page content */}
    </PageTransition>
  );
}
```

---

### 1.3 Stat Card with Animated Counter

**shadcn/ui components:** `Card`, `CardContent`, `CardHeader`

```tsx
// components/animated-stat-card.tsx
"use client";

import { useEffect, useRef } from "react";
import { useMotionValue, useTransform, animate, motion } from "motion/react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: number;
  suffix?: string;
  decimals?: number;
  icon: LucideIcon;
  trend?: "up" | "down" | "neutral";
  trendValue?: string;
}

export function AnimatedStatCard({
  label,
  value,
  suffix = "",
  decimals = 0,
  icon: Icon,
  trend,
  trendValue,
}: StatCardProps) {
  const motionValue = useMotionValue(0);
  const rounded = useTransform(motionValue, (latest) =>
    decimals === 0
      ? Math.round(latest).toString()
      : latest.toFixed(decimals)
  );

  useEffect(() => {
    const controls = animate(motionValue, value, {
      duration: 1.2,
      ease: "easeOut",
    });
    return controls.stop;
  }, [value, motionValue]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <span className="text-sm font-medium text-slate-500">{label}</span>
          <Icon size={16} className="text-slate-400" />
        </CardHeader>
        <CardContent>
          <div className="flex items-baseline gap-1">
            <motion.span className="text-2xl font-bold text-slate-900">
              {rounded}
            </motion.span>
            {suffix && (
              <span className="text-sm text-slate-500">{suffix}</span>
            )}
          </div>
          {trendValue && (
            <p
              className={
                trend === "up"
                  ? "mt-1 text-xs text-emerald-600"
                  : trend === "down"
                  ? "mt-1 text-xs text-red-500"
                  : "mt-1 text-xs text-slate-400"
              }
            >
              {trendValue}
            </p>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
```

---

### 1.4 Status Badge with Pulse Animation

**shadcn/ui components:** `Badge`

```tsx
// components/status-badge.tsx
"use client";

import { motion } from "motion/react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type StatusType = "healthy" | "warning" | "critical" | "pending" | "tracing";

const statusConfig: Record<
  StatusType,
  { label: string; dotColor: string; badgeClass: string }
> = {
  healthy:  { label: "Healthy",  dotColor: "bg-emerald-500", badgeClass: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  warning:  { label: "Warning",  dotColor: "bg-amber-500",   badgeClass: "border-amber-200 bg-amber-50 text-amber-700" },
  critical: { label: "Critical", dotColor: "bg-red-500",     badgeClass: "border-red-200 bg-red-50 text-red-700" },
  pending:  { label: "Pending",  dotColor: "bg-slate-400",   badgeClass: "border-slate-200 bg-slate-50 text-slate-600" },
  tracing:  { label: "Tracing",  dotColor: "bg-violet-500",  badgeClass: "border-violet-200 bg-violet-50 text-violet-700" },
};

export function StatusBadge({
  status,
  label,
}: {
  status: StatusType;
  label?: string;
}) {
  const config = statusConfig[status];
  const shouldPulse = status === "tracing" || status === "warning";

  return (
    <Badge
      variant="outline"
      className={cn("gap-1.5 py-0.5 text-xs font-medium", config.badgeClass)}
    >
      <span className="relative flex h-2 w-2">
        {shouldPulse && (
          <motion.span
            className={cn("absolute inline-flex h-full w-full rounded-full opacity-75", config.dotColor)}
            animate={{ scale: [1, 1.8, 1], opacity: [0.75, 0, 0.75] }}
            transition={{ duration: 1.5, repeat: Infinity, ease: "easeOut" }}
          />
        )}
        <span
          className={cn("relative inline-flex h-2 w-2 rounded-full", config.dotColor)}
        />
      </span>
      {label ?? config.label}
    </Badge>
  );
}
```

---

### 1.5 Loading Skeleton Animation

**shadcn/ui components:** `Skeleton`

```tsx
// components/skeletons.tsx
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

export function StatCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-2">
        <Skeleton className="h-4 w-24" />
      </CardHeader>
      <CardContent>
        <Skeleton className="mb-2 h-8 w-16" />
        <Skeleton className="h-3 w-32" />
      </CardContent>
    </Card>
  );
}

export function TableRowSkeleton({ cols = 5 }: { cols?: number }) {
  return (
    <tr>
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <Skeleton className="h-4 w-full" />
        </td>
      ))}
    </tr>
  );
}

export function ChatBubbleSkeleton() {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-end gap-2">
        <Skeleton className="h-8 w-8 rounded-full" />
        <Skeleton className="h-12 w-64 rounded-2xl rounded-bl-none" />
      </div>
      <div className="flex items-end justify-end gap-2">
        <Skeleton className="h-16 w-80 rounded-2xl rounded-br-none" />
      </div>
    </div>
  );
}
```

---

### 1.6 Staggered List Entrance Animation

```tsx
// components/stagger-list.tsx
"use client";

import { motion } from "motion/react";

// Parent container — controls stagger timing
const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.06,
      delayChildren: 0.1,
    },
  },
};

// Each child item
const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.22 } },
};

interface StaggerListProps<T> {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  className?: string;
}

export function StaggerList<T>({
  items,
  renderItem,
  className,
}: StaggerListProps<T>) {
  return (
    <motion.ul
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className={className}
    >
      {items.map((item, i) => (
        <motion.li key={i} variants={itemVariants}>
          {renderItem(item, i)}
        </motion.li>
      ))}
    </motion.ul>
  );
}

// One-off usage for grids (cards, not lists):
export function StaggerGrid({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
    >
      {children}
    </motion.div>
  );
}

export const staggerItemVariants = itemVariants;
```

---

## 2. Demo Home (`page.tsx`)

### 2.1 Component Composition

```
PageTransition
└── div.max-w-5xl.mx-auto
    ├── HeroSection          ← fade-up + stagger
    ├── LoopDiagram          ← 7-stage animated cycle
    ├── SystemHealthGrid     ← 4 stat cards, stagger entrance
    ├── QuickStartActions    ← 2 CTA buttons
    └── ActivityFeed         ← stagger list
```

---

### 2.2 Hero Section — Fade-Up Entrance

```tsx
// components/demo-home/hero-section.tsx
"use client";

import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/status-badge";
import { Zap } from "lucide-react";

const fadeUp = (delay = 0) => ({
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.4, delay, ease: [0.25, 0.1, 0.25, 1] },
});

export function HeroSection() {
  return (
    <section className="mb-10 text-center">
      <motion.div {...fadeUp(0)} className="mb-3 flex justify-center">
        <StatusBadge status="healthy" label="All systems operational" />
      </motion.div>

      <motion.h1
        {...fadeUp(0.08)}
        className="mb-3 text-4xl font-bold tracking-tight text-slate-900"
      >
        PhoenixLoop
      </motion.h1>

      <motion.p
        {...fadeUp(0.14)}
        className="mx-auto mb-6 max-w-lg text-slate-500"
      >
        A Gemini support agent that detects its own failures through Phoenix
        and fixes itself with evidence.
      </motion.p>

      <motion.div {...fadeUp(0.2)} className="flex justify-center gap-3">
        <Button size="lg" className="gap-2">
          <Zap size={16} />
          Run Demo Scenario
        </Button>
        <Button size="lg" variant="outline">
          View Last Healing Cycle
        </Button>
      </motion.div>
    </section>
  );
}
```

---

### 2.3 Self-Healing Loop Diagram (7 Stages)

```tsx
// components/demo-home/loop-diagram.tsx
"use client";

import { motion } from "motion/react";

const STAGES = [
  { id: 1, label: "Trace",      icon: "🔍", color: "bg-violet-100 text-violet-700 border-violet-200" },
  { id: 2, label: "Evaluate",   icon: "📊", color: "bg-blue-100 text-blue-700 border-blue-200" },
  { id: 3, label: "Detect",     icon: "⚠️",  color: "bg-amber-100 text-amber-700 border-amber-200" },
  { id: 4, label: "Diagnose",   icon: "🔬", color: "bg-orange-100 text-orange-700 border-orange-200" },
  { id: 5, label: "Repair",     icon: "🔧", color: "bg-red-100 text-red-700 border-red-200" },
  { id: 6, label: "Experiment", icon: "🧪", color: "bg-emerald-100 text-emerald-700 border-emerald-200" },
  { id: 7, label: "Gate",       icon: "🛡️", color: "bg-slate-100 text-slate-700 border-slate-200" },
];

// Positions on an ellipse. cx=50%, cy=50%, rx=38%, ry=30%
function stagePosition(index: number, total: number) {
  const angle = (index / total) * 2 * Math.PI - Math.PI / 2;
  const x = 50 + 38 * Math.cos(angle);
  const y = 50 + 30 * Math.sin(angle);
  return { x, y };
}

export function LoopDiagram({ activeStage = 0 }: { activeStage?: number }) {
  return (
    <div className="relative mx-auto mb-10 h-64 w-full max-w-lg select-none">
      {/* Dashed orbit ring */}
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        <ellipse
          cx="50"
          cy="50"
          rx="38"
          ry="30"
          fill="none"
          stroke="#e2e8f0"
          strokeWidth="0.5"
          strokeDasharray="2 2"
        />
        {/* Animated traveling dot */}
        <motion.circle
          r="1.2"
          fill="#f97316"
          style={{ offsetPath: "path('M 50 20 A 38 30 0 1 1 49.99 20')" } as React.CSSProperties}
          animate={{ offsetDistance: ["0%", "100%"] }}
          transition={{ duration: 6, repeat: Infinity, ease: "linear" }}
        />
      </svg>

      {/* Stage nodes */}
      {STAGES.map((stage, i) => {
        const { x, y } = stagePosition(i, STAGES.length);
        const isActive = i + 1 === activeStage;
        return (
          <motion.div
            key={stage.id}
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.07, type: "spring", stiffness: 260, damping: 20 }}
            style={{
              position: "absolute",
              left: `${x}%`,
              top: `${y}%`,
              transform: "translate(-50%, -50%)",
            }}
          >
            <motion.div
              animate={isActive ? { scale: [1, 1.12, 1] } : {}}
              transition={{ duration: 1.4, repeat: Infinity }}
              className={`flex flex-col items-center gap-0.5 rounded-xl border px-2.5 py-1.5 text-xs font-medium shadow-sm ${stage.color} ${isActive ? "ring-2 ring-orange-400 ring-offset-1" : ""}`}
            >
              <span>{stage.icon}</span>
              <span>{stage.label}</span>
            </motion.div>
          </motion.div>
        );
      })}
    </div>
  );
}
```

---

### 2.4 Activity Feed with List Entrance

**shadcn/ui components:** `ScrollArea`, `Avatar`, `AvatarFallback`, `Badge`, `Separator`

```tsx
// components/demo-home/activity-feed.tsx
"use client";

import { motion } from "motion/react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

interface ActivityEvent {
  id: string;
  time: string;
  actor: string;
  action: string;
  tag: "eval" | "failure" | "repair" | "deploy";
}

const tagStyles: Record<ActivityEvent["tag"], string> = {
  eval:    "border-blue-200 bg-blue-50 text-blue-700",
  failure: "border-red-200 bg-red-50 text-red-700",
  repair:  "border-amber-200 bg-amber-50 text-amber-700",
  deploy:  "border-emerald-200 bg-emerald-50 text-emerald-700",
};

export function ActivityFeed({ events }: { events: ActivityEvent[] }) {
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-slate-700">Recent Activity</h3>
      <ScrollArea className="h-72 rounded-lg border border-slate-200 bg-white px-4 py-2">
        <motion.div
          initial="hidden"
          animate="show"
          variants={{
            hidden: {},
            show: { transition: { staggerChildren: 0.05 } },
          }}
          className="flex flex-col gap-0"
        >
          {events.map((event, i) => (
            <motion.div
              key={event.id}
              variants={{
                hidden: { opacity: 0, x: -10 },
                show:   { opacity: 1, x: 0, transition: { duration: 0.2 } },
              }}
            >
              <div className="flex items-start gap-3 py-2.5">
                <span className="mt-0.5 text-xs text-slate-400 tabular-nums w-14 shrink-0">
                  {event.time}
                </span>
                <div className="flex flex-1 flex-wrap items-center gap-1.5">
                  <span className="text-xs font-medium text-slate-700">{event.actor}</span>
                  <span className="text-xs text-slate-500">{event.action}</span>
                  <Badge variant="outline" className={`text-[10px] py-0 ${tagStyles[event.tag]}`}>
                    {event.tag}
                  </Badge>
                </div>
              </div>
              {i < events.length - 1 && <Separator />}
            </motion.div>
          ))}
        </motion.div>
      </ScrollArea>
    </div>
  );
}
```

---

## 3. Support Conversation

### 3.1 Component Composition

```
PageTransition
└── div.flex.h-full.gap-4
    ├── div.flex-1 (chat panel)
    │   ├── ScenarioSelector    ← Select component
    │   ├── ScrollArea (messages)
    │   │   └── AnimatePresence
    │   │       ├── ChatBubble (user, motion slide from right)
    │   │       ├── ChatBubble (agent, motion slide from left)
    │   │       ├── TypingIndicator
    │   │       └── ToolCallCard (Collapsible)
    │   └── Input + Button (send)
    └── div.w-72 (right panel)
        ├── PhoenixTraceIndicator
        └── EvalBadgeRow
```

---

### 3.2 Chat Bubble Animations

```tsx
// components/conversation/chat-bubble.tsx
"use client";

import { motion } from "motion/react";
import { cn } from "@/lib/utils";

interface ChatBubbleProps {
  role: "user" | "agent";
  content: string;
  timestamp?: string;
}

// Variants keyed by role
const bubbleVariants = {
  user: {
    initial: { opacity: 0, x: 20, scale: 0.96 },
    animate: { opacity: 1, x: 0,  scale: 1 },
  },
  agent: {
    initial: { opacity: 0, x: -20, scale: 0.96 },
    animate: { opacity: 1, x: 0,   scale: 1 },
  },
};

export function ChatBubble({ role, content, timestamp }: ChatBubbleProps) {
  const isUser = role === "user";
  const variants = bubbleVariants[role];

  return (
    <motion.div
      initial={variants.initial}
      animate={variants.animate}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ type: "spring", stiffness: 340, damping: 28 }}
      className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}
      layout
    >
      <div
        className={cn(
          "max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm",
          isUser
            ? "rounded-br-sm bg-slate-900 text-white"
            : "rounded-bl-sm border border-slate-200 bg-white text-slate-800"
        )}
      >
        {content}
        {timestamp && (
          <p
            className={cn(
              "mt-1 text-[10px]",
              isUser ? "text-slate-400" : "text-slate-400"
            )}
          >
            {timestamp}
          </p>
        )}
      </div>
    </motion.div>
  );
}
```

Usage with `AnimatePresence`:
```tsx
import { AnimatePresence } from "motion/react";

<AnimatePresence initial={false}>
  {messages.map((msg) => (
    <ChatBubble key={msg.id} role={msg.role} content={msg.content} />
  ))}
  {isTyping && <TypingIndicator key="typing" />}
</AnimatePresence>
```

---

### 3.3 Typing Indicator Animation

```tsx
// components/conversation/typing-indicator.tsx
"use client";

import { motion } from "motion/react";

export function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 4 }}
      transition={{ duration: 0.2 }}
      className="flex items-center justify-start"
    >
      <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-3 shadow-sm">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="h-2 w-2 rounded-full bg-slate-400"
            animate={{ y: [0, -4, 0] }}
            transition={{
              duration: 0.6,
              repeat: Infinity,
              delay: i * 0.12,
              ease: "easeInOut",
            }}
          />
        ))}
      </div>
    </motion.div>
  );
}
```

---

### 3.4 Tool Call Collapsible Card

**shadcn/ui components:** `Collapsible`, `CollapsibleTrigger`, `CollapsibleContent`, `Badge`

```tsx
// components/conversation/tool-call-card.tsx
"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import { ChevronRight, Wrench, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface ToolCallCardProps {
  toolName: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  status: "success" | "error";
  latencyMs: number;
}

export function ToolCallCard({
  toolName,
  input,
  output,
  status,
  latencyMs,
}: ToolCallCardProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97, y: 6 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="my-1 ml-4"
    >
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 hover:bg-slate-100">
          <Wrench size={12} className="shrink-0 text-slate-400" />
          <span className="font-mono font-medium">{toolName}</span>
          <Badge
            variant="outline"
            className={cn(
              "ml-auto text-[10px] py-0",
              status === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                : "border-red-200 bg-red-50 text-red-700"
            )}
          >
            {status === "success" ? (
              <CheckCircle2 size={10} className="mr-0.5" />
            ) : (
              <XCircle size={10} className="mr-0.5" />
            )}
            {latencyMs}ms
          </Badge>
          <motion.span
            animate={{ rotate: isOpen ? 90 : 0 }}
            transition={{ duration: 0.15 }}
          >
            <ChevronRight size={12} className="text-slate-400" />
          </motion.span>
        </CollapsibleTrigger>

        <AnimatePresence>
          {isOpen && (
            <CollapsibleContent forceMount asChild>
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.18 }}
                className="overflow-hidden"
              >
                <div className="mt-1 rounded-lg border border-slate-200 bg-white p-3 font-mono text-[11px] text-slate-600">
                  <div className="mb-2">
                    <span className="font-semibold text-slate-400">INPUT</span>
                    <pre className="mt-1 overflow-x-auto">
                      {JSON.stringify(input, null, 2)}
                    </pre>
                  </div>
                  <div>
                    <span className="font-semibold text-slate-400">OUTPUT</span>
                    <pre className="mt-1 overflow-x-auto">
                      {JSON.stringify(output, null, 2)}
                    </pre>
                  </div>
                </div>
              </motion.div>
            </CollapsibleContent>
          )}
        </AnimatePresence>
      </Collapsible>
    </motion.div>
  );
}
```

---

### 3.5 Phoenix Trace Pulse Indicator

```tsx
// components/conversation/trace-indicator.tsx
"use client";

import { motion, AnimatePresence } from "motion/react";

export function PhoenixTraceIndicator({ isTracing }: { isTracing: boolean }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs">
      <span className="relative flex h-2.5 w-2.5">
        <AnimatePresence>
          {isTracing && (
            <motion.span
              key="pulse"
              className="absolute inline-flex h-full w-full rounded-full bg-violet-400"
              initial={{ opacity: 0.7, scale: 1 }}
              animate={{ opacity: 0, scale: 2.5 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.9, repeat: Infinity }}
            />
          )}
        </AnimatePresence>
        <span
          className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
            isTracing ? "bg-violet-500" : "bg-slate-300"
          }`}
        />
      </span>
      <span className={isTracing ? "text-violet-700 font-medium" : "text-slate-400"}>
        {isTracing ? "Tracing to Phoenix..." : "No active trace"}
      </span>
    </div>
  );
}
```

---

### 3.6 Eval Badge Row Animation

```tsx
// components/conversation/eval-badge-row.tsx
"use client";

import { motion } from "motion/react";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, XCircle, Minus } from "lucide-react";

interface EvalScore {
  name: string;
  outcome: "pass" | "fail" | "pending";
  score?: number;
}

export function EvalBadgeRow({ evals }: { evals: EvalScore[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {evals.map((ev, i) => (
        <motion.div
          key={ev.name}
          initial={{ opacity: 0, scale: 0.7 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: i * 0.04, type: "spring", stiffness: 300, damping: 20 }}
        >
          <Badge
            variant="outline"
            className={
              ev.outcome === "pass"
                ? "border-emerald-200 bg-emerald-50 text-emerald-700 text-[10px] gap-0.5"
                : ev.outcome === "fail"
                ? "border-red-200 bg-red-50 text-red-700 text-[10px] gap-0.5"
                : "border-slate-200 bg-slate-50 text-slate-500 text-[10px] gap-0.5"
            }
          >
            {ev.outcome === "pass" && <CheckCircle2 size={9} />}
            {ev.outcome === "fail" && <XCircle size={9} />}
            {ev.outcome === "pending" && <Minus size={9} />}
            {ev.name}
            {ev.score !== undefined && ` ${(ev.score * 100).toFixed(0)}%`}
          </Badge>
        </motion.div>
      ))}
    </div>
  );
}
```

---

## 4. Trace & Eval View

### 4.1 Component Composition

```
PageTransition
└── div.flex.gap-4
    ├── div.flex-1 (waterfall)
    │   ├── Card (session summary header)
    │   ├── Tabs (Waterfall | Annotations | Raw)
    │   │   └── TraceWaterfall
    │   │       └── SpanRow × n (nested, clickable)
    └── AnimatePresence
        └── SpanDetailPanel (slide-in from right)
```

---

### 4.2 Trace Waterfall — Horizontal Span Bars

```tsx
// components/traces/trace-waterfall.tsx
"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface Span {
  spanId: string;
  name: string;
  startMs: number;  // offset from trace start
  durationMs: number;
  depth: number;    // nesting level
  evalOutcome?: "pass" | "fail";
  kind: "llm" | "tool" | "agent" | "eval";
}

const kindColors: Record<Span["kind"], string> = {
  agent: "bg-violet-400",
  llm:   "bg-blue-400",
  tool:  "bg-amber-400",
  eval:  "bg-emerald-400",
};

interface TraceWaterfallProps {
  spans: Span[];
  totalDurationMs: number;
  onSpanClick?: (span: Span) => void;
}

export function TraceWaterfall({
  spans,
  totalDurationMs,
  onSpanClick,
}: TraceWaterfallProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  return (
    <div className="space-y-1 font-mono text-xs">
      {spans.map((span, i) => {
        const leftPct  = (span.startMs / totalDurationMs) * 100;
        const widthPct = Math.max((span.durationMs / totalDurationMs) * 100, 0.5);

        return (
          <motion.div
            key={span.spanId}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.025, duration: 0.18 }}
            className={cn(
              "flex cursor-pointer items-center gap-2 rounded px-1 py-0.5",
              hoveredId === span.spanId ? "bg-slate-50" : "hover:bg-slate-50"
            )}
            onMouseEnter={() => setHoveredId(span.spanId)}
            onMouseLeave={() => setHoveredId(null)}
            onClick={() => onSpanClick?.(span)}
          >
            {/* Indent spacer */}
            <div style={{ width: span.depth * 16 }} className="shrink-0" />

            {/* Span name */}
            <span className="w-44 truncate text-slate-700 shrink-0">
              {span.name}
            </span>

            {/* Bar track */}
            <div className="relative h-4 flex-1 overflow-hidden rounded bg-slate-100">
              <motion.div
                className={cn("absolute top-0 h-full rounded", kindColors[span.kind])}
                style={{ left: `${leftPct}%` }}
                initial={{ width: 0 }}
                animate={{ width: `${widthPct}%` }}
                transition={{ delay: i * 0.025 + 0.1, duration: 0.35, ease: "easeOut" }}
              />
            </div>

            {/* Duration */}
            <span className="w-16 text-right text-slate-400 shrink-0">
              {span.durationMs}ms
            </span>

            {/* Eval badge */}
            {span.evalOutcome && (
              <Badge
                variant="outline"
                className={cn(
                  "shrink-0 text-[9px] py-0",
                  span.evalOutcome === "pass"
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                    : "border-red-200 bg-red-50 text-red-700"
                )}
              >
                {span.evalOutcome}
              </Badge>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}
```

---

### 4.3 Span Detail Slide-In Panel

```tsx
// components/traces/span-detail-panel.tsx
"use client";

import { motion } from "motion/react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { EvalBadgeRow } from "@/components/conversation/eval-badge-row";

interface SpanDetailPanelProps {
  span: {
    name: string;
    spanId: string;
    durationMs: number;
    evals?: Array<{ name: string; outcome: "pass" | "fail"; score?: number }>;
    attributes?: Record<string, string>;
  };
  onClose: () => void;
}

export function SpanDetailPanel({ span, onClose }: SpanDetailPanelProps) {
  return (
    <motion.aside
      key="span-detail"
      initial={{ x: "100%", opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: "100%", opacity: 0 }}
      transition={{ type: "spring", stiffness: 320, damping: 32 }}
      className="flex h-full w-80 flex-col border-l border-slate-200 bg-white"
    >
      <div className="flex items-center justify-between px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800 truncate">{span.name}</h3>
        <Button variant="ghost" size="icon" onClick={onClose} className="h-6 w-6">
          <X size={14} />
        </Button>
      </div>

      <Separator />

      <ScrollArea className="flex-1 px-4 py-3">
        <div className="space-y-4 text-xs">
          <div>
            <span className="font-semibold text-slate-500">SPAN ID</span>
            <p className="mt-1 font-mono text-slate-700 break-all">{span.spanId}</p>
          </div>

          <div>
            <span className="font-semibold text-slate-500">DURATION</span>
            <p className="mt-1 text-slate-700">{span.durationMs}ms</p>
          </div>

          {span.evals && span.evals.length > 0 && (
            <div>
              <span className="font-semibold text-slate-500 block mb-2">EVALUATORS</span>
              <EvalBadgeRow evals={span.evals} />
            </div>
          )}

          {span.attributes && (
            <div>
              <span className="font-semibold text-slate-500">ATTRIBUTES</span>
              <div className="mt-1 space-y-1 rounded-md border border-slate-100 bg-slate-50 p-2 font-mono">
                {Object.entries(span.attributes).map(([k, v]) => (
                  <div key={k} className="flex gap-2">
                    <span className="text-slate-400 shrink-0">{k}:</span>
                    <span className="text-slate-700 break-all">{v}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </ScrollArea>
    </motion.aside>
  );
}
```

---

### 4.4 Tab Transitions

```tsx
// components/traces/eval-tabs.tsx
"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

export function EvalTabs() {
  const [tab, setTab] = useState("waterfall");

  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList className="mb-4">
        <TabsTrigger value="waterfall">Waterfall</TabsTrigger>
        <TabsTrigger value="annotations">Annotations</TabsTrigger>
        <TabsTrigger value="raw">Raw JSON</TabsTrigger>
      </TabsList>

      <AnimatePresence mode="wait">
        <motion.div
          key={tab}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.16 }}
        >
          {tab === "waterfall" && <TabsContent value="waterfall" forceMount>{/* TraceWaterfall */}</TabsContent>}
          {tab === "annotations" && <TabsContent value="annotations" forceMount>{/* Annotation table */}</TabsContent>}
          {tab === "raw" && <TabsContent value="raw" forceMount>{/* JSON viewer */}</TabsContent>}
        </motion.div>
      </AnimatePresence>
    </Tabs>
  );
}
```

---

## 5. Failure Trends

### 5.1 Component Composition

```
PageTransition
└── div.space-y-6
    ├── div.grid.grid-cols-4 (animated stat counters)
    ├── Card (FailureAreaChart with threshold line)
    └── Card (FailureTable with highlight animation)
```

---

### 5.2 Recharts Area Chart with Threshold Line

```tsx
// components/failures/failure-area-chart.tsx
"use client";

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer, Legend,
} from "recharts";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

interface FailureDataPoint {
  date: string;
  failure_rate: number;
  occurrence_count: number;
}

const THRESHOLD = 0.30; // 30% failure rate threshold from config

export function FailureAreaChart({ data }: { data: FailureDataPoint[] }) {
  return (
    <Card>
      <CardHeader>
        <h3 className="text-sm font-semibold text-slate-700">Failure Rate Over Time</h3>
        <p className="text-xs text-slate-400">Dashed line = improvement trigger threshold (30%)</p>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="failureGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: "#94a3b8" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
              tick={{ fontSize: 11, fill: "#94a3b8" }}
              axisLine={false}
              tickLine={false}
              domain={[0, 0.6]}
            />
            <Tooltip
              contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
              formatter={(value: number) => [`${(value * 100).toFixed(1)}%`, "Failure Rate"]}
            />

            {/* Threshold reference line */}
            <ReferenceLine
              y={THRESHOLD}
              stroke="#f97316"
              strokeDasharray="5 3"
              strokeWidth={1.5}
              label={{
                value: "Threshold",
                position: "insideTopRight",
                fontSize: 10,
                fill: "#f97316",
              }}
            />

            <Area
              type="monotone"
              dataKey="failure_rate"
              stroke="#ef4444"
              strokeWidth={2}
              fill="url(#failureGradient)"
              dot={false}
              activeDot={{ r: 4, fill: "#ef4444" }}
              isAnimationActive={true}
              animationDuration={800}
              animationEasing="ease-out"
            />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
```

---

### 5.3 Failure Table with Row Highlight for Threshold Breaches

**shadcn/ui components:** `Table`, `TableHeader`, `TableRow`, `TableHead`, `TableBody`, `TableCell`, `Badge`

```tsx
// components/failures/failure-table.tsx
"use client";

import { motion } from "motion/react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Stethoscope } from "lucide-react";

interface FailureRow {
  failureKey: string;
  summary: string;
  evaluatorName: string;
  occurrenceCount: number;
  isAboveThreshold: boolean;
  lastSeenAt: string;
}

interface FailureTableProps {
  rows: FailureRow[];
  onDiagnose: (failureKey: string) => void;
}

export function FailureTable({ rows, onDiagnose }: FailureTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Failure Pattern</TableHead>
          <TableHead>Evaluator</TableHead>
          <TableHead className="text-right">Count</TableHead>
          <TableHead>Last Seen</TableHead>
          <TableHead />
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, i) => (
          <motion.tr
            key={row.failureKey}
            initial={{ opacity: 0, backgroundColor: "rgba(0,0,0,0)" }}
            animate={{
              opacity: 1,
              backgroundColor: row.isAboveThreshold
                ? ["rgba(254,215,170,0.4)", "rgba(254,215,170,0.15)"]
                : "rgba(0,0,0,0)",
            }}
            transition={{
              opacity: { delay: i * 0.04, duration: 0.2 },
              backgroundColor: { delay: i * 0.04 + 0.3, duration: 1.2, ease: "easeOut" },
            }}
            className="border-b border-slate-100"
          >
            <TableCell>
              <div className="flex items-center gap-2">
                {row.isAboveThreshold && (
                  <AlertTriangle size={13} className="text-orange-500 shrink-0" />
                )}
                <span className="text-sm text-slate-700 line-clamp-1">{row.summary}</span>
              </div>
            </TableCell>
            <TableCell>
              <Badge variant="outline" className="font-mono text-[10px]">
                {row.evaluatorName}
              </Badge>
            </TableCell>
            <TableCell className="text-right">
              <span
                className={`text-sm font-semibold tabular-nums ${
                  row.isAboveThreshold ? "text-red-600" : "text-slate-700"
                }`}
              >
                {row.occurrenceCount}
              </span>
            </TableCell>
            <TableCell className="text-xs text-slate-400">{row.lastSeenAt}</TableCell>
            <TableCell>
              {row.isAboveThreshold && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onDiagnose(row.failureKey)}
                  className="h-7 gap-1 text-xs"
                >
                  <Stethoscope size={11} />
                  Diagnose
                </Button>
              )}
            </TableCell>
          </motion.tr>
        ))}
      </TableBody>
    </Table>
  );
}
```

---

## 6. Improvement Proposal

### 6.1 Component Composition

```
PageTransition
└── div.grid.grid-cols-3.gap-4
    ├── div.col-span-2
    │   ├── EvidenceCards        ← Collapsible accordion
    │   ├── MCPQueryLog          ← Terminal-style animated log
    │   ├── PromptDiffView       ← Side-by-side red/green diff
    │   └── RegressionTestList   ← Stagger list
    └── div.col-span-1
        ├── DiagnosisCard
        └── ApproveRejectButtons
```

---

### 6.2 Evidence Cards Accordion

**shadcn/ui components:** `Collapsible`, `CollapsibleTrigger`, `CollapsibleContent`, `Card`

```tsx
// components/improvements/evidence-cards.tsx
"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import { ChevronDown, ExternalLink } from "lucide-react";

interface EvidenceItem {
  traceId: string;
  summary: string;
  failureKey: string;
  phoenixUrl?: string;
}

export function EvidenceCards({ items }: { items: EvidenceItem[] }) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        Phoenix Evidence ({items.length} traces)
      </h3>
      {items.map((item, i) => (
        <motion.div
          key={item.traceId}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.06 }}
        >
          <Collapsible
            open={openId === item.traceId}
            onOpenChange={(open) => setOpenId(open ? item.traceId : null)}
          >
            <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-xs hover:bg-slate-50">
              <Badge variant="outline" className="font-mono text-[10px] text-red-600 border-red-200 bg-red-50">
                {item.failureKey}
              </Badge>
              <span className="flex-1 truncate text-left text-slate-700">{item.summary}</span>
              {item.phoenixUrl && (
                <a
                  href={item.phoenixUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="text-violet-500 hover:text-violet-700"
                >
                  <ExternalLink size={11} />
                </a>
              )}
              <motion.span
                animate={{ rotate: openId === item.traceId ? 180 : 0 }}
                transition={{ duration: 0.15 }}
              >
                <ChevronDown size={12} className="text-slate-400" />
              </motion.span>
            </CollapsibleTrigger>

            <AnimatePresence>
              {openId === item.traceId && (
                <CollapsibleContent forceMount asChild>
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="mt-1 rounded-b-lg border border-t-0 border-slate-200 bg-slate-50 p-3 font-mono text-[11px] text-slate-600">
                      <span className="text-slate-400">trace_id: </span>{item.traceId}
                    </div>
                  </motion.div>
                </CollapsibleContent>
              )}
            </AnimatePresence>
          </Collapsible>
        </motion.div>
      ))}
    </div>
  );
}
```

---

### 6.3 MCP Query Log (Terminal-Style)

```tsx
// components/improvements/mcp-query-log.tsx
"use client";

import { useEffect, useRef } from "react";
import { motion } from "motion/react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";

interface McpLogEntry {
  id: string;
  timestamp: string;
  direction: "read" | "write";
  tool: string;
  summary: string;
  status: "pending" | "success" | "error";
}

export function McpQueryLog({ entries }: { entries: McpLogEntry[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries.length]);

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950 p-1">
      <div className="flex items-center gap-1.5 border-b border-slate-800 px-3 py-2">
        <span className="h-2.5 w-2.5 rounded-full bg-red-500 opacity-80" />
        <span className="h-2.5 w-2.5 rounded-full bg-amber-500 opacity-80" />
        <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 opacity-80" />
        <span className="ml-2 text-[10px] text-slate-500">Phoenix MCP — Query Log</span>
      </div>

      <ScrollArea className="h-48 px-3 py-2">
        <div className="space-y-1 font-mono text-[11px]">
          {entries.map((entry, i) => (
            <motion.div
              key={entry.id}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.08, duration: 0.2 }}
              className="flex items-start gap-2"
            >
              <span className="text-slate-600 shrink-0 tabular-nums">{entry.timestamp}</span>
              <Badge
                variant="outline"
                className={`shrink-0 py-0 text-[9px] ${
                  entry.direction === "write"
                    ? "border-orange-800 bg-orange-950 text-orange-400"
                    : "border-violet-800 bg-violet-950 text-violet-400"
                }`}
              >
                {entry.direction.toUpperCase()}
              </Badge>
              <span className="text-emerald-400">{entry.tool}</span>
              <span className="text-slate-400">{entry.summary}</span>
              {entry.status === "success" && (
                <span className="ml-auto text-emerald-500 shrink-0">✓</span>
              )}
              {entry.status === "error" && (
                <span className="ml-auto text-red-400 shrink-0">✗</span>
              )}
              {entry.status === "pending" && (
                <motion.span
                  className="ml-auto text-amber-400 shrink-0"
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 0.9, repeat: Infinity }}
                >
                  …
                </motion.span>
              )}
            </motion.div>
          ))}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>
    </div>
  );
}
```

---

### 6.4 Prompt Diff View (Side-by-Side)

```tsx
// components/improvements/prompt-diff.tsx
"use client";

import { motion } from "motion/react";
import { ScrollArea } from "@/components/ui/scroll-area";

type DiffLine = { type: "removed" | "added" | "context"; text: string };

interface PromptDiffProps {
  baselineLines: DiffLine[];
  candidateLines: DiffLine[];
}

function DiffPanel({
  title,
  lines,
  side,
}: {
  title: string;
  lines: DiffLine[];
  side: "baseline" | "candidate";
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: side === "baseline" ? -12 : 12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.28 }}
      className="flex-1 min-w-0"
    >
      <div
        className={`rounded-t-lg border px-3 py-1.5 text-xs font-semibold ${
          side === "baseline"
            ? "border-red-200 bg-red-50 text-red-700"
            : "border-emerald-200 bg-emerald-50 text-emerald-700"
        }`}
      >
        {title}
      </div>
      <ScrollArea className="h-72 rounded-b-lg border border-t-0 border-slate-200 bg-white">
        <div className="p-3 font-mono text-[11px] leading-relaxed">
          {lines.map((line, i) => (
            <div
              key={i}
              className={`whitespace-pre-wrap rounded px-1 ${
                line.type === "removed"
                  ? "bg-red-50 text-red-700"
                  : line.type === "added"
                  ? "bg-emerald-50 text-emerald-700"
                  : "text-slate-600"
              }`}
            >
              <span className="mr-2 select-none text-slate-300">
                {line.type === "removed" ? "−" : line.type === "added" ? "+" : " "}
              </span>
              {line.text}
            </div>
          ))}
        </div>
      </ScrollArea>
    </motion.div>
  );
}

export function PromptDiffView({ baselineLines, candidateLines }: PromptDiffProps) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Prompt Diff
      </h3>
      <div className="flex gap-2">
        <DiffPanel title="Baseline (production)" lines={baselineLines} side="baseline" />
        <DiffPanel title="Candidate (proposed)" lines={candidateLines} side="candidate" />
      </div>
    </div>
  );
}
```

---

## 7. Experiment Results

### 7.1 Component Composition

```
PageTransition
└── div.space-y-6
    ├── div.grid.grid-cols-2.gap-4 (ScoreComparisonCards)
    ├── Card (GroupedBarChart — per-evaluator breakdown)
    ├── VerdictBadge (scale-up entrance)
    └── Card (RegressionResultsTable)
```

---

### 7.2 Score Comparison Cards

```tsx
// components/experiments/score-comparison-cards.tsx
"use client";

import { motion } from "motion/react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ArrowUp, ArrowDown, Minus } from "lucide-react";

interface ScoreCardProps {
  label: "Baseline" | "Candidate";
  releaseScore: number;
  criticalFailureRate: number;
  hallucinationRate: number;
  regressionPassRate: number;
  latencyP50Ms: number;
}

export function ScoreComparisonCards({
  baseline,
  candidate,
}: {
  baseline: ScoreCardProps;
  candidate: ScoreCardProps;
}) {
  const delta = candidate.releaseScore - baseline.releaseScore;

  return (
    <div className="grid grid-cols-2 gap-4">
      {[baseline, candidate].map((card, i) => {
        const isCandidate = i === 1;
        return (
          <motion.div
            key={card.label}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1, duration: 0.3 }}
          >
            <Card className={isCandidate ? "border-emerald-200 ring-1 ring-emerald-100" : ""}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-slate-700">{card.label}</span>
                  {isCandidate && (
                    <Badge
                      variant="outline"
                      className="border-emerald-200 bg-emerald-50 text-emerald-700 text-xs gap-1"
                    >
                      {delta > 0 ? <ArrowUp size={11} /> : delta < 0 ? <ArrowDown size={11} /> : <Minus size={11} />}
                      {delta > 0 ? "+" : ""}{(delta * 100).toFixed(1)}%
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-3 text-xs">
                <div>
                  <div className="mb-1 flex justify-between text-slate-500">
                    <span>Release Score</span>
                    <span className="font-semibold text-slate-800 tabular-nums">
                      {(card.releaseScore * 100).toFixed(1)}%
                    </span>
                  </div>
                  <Progress
                    value={card.releaseScore * 100}
                    className="h-2"
                  />
                </div>

                {[
                  { label: "Critical Failures",    value: card.criticalFailureRate,  bad: true },
                  { label: "Hallucination Rate",   value: card.hallucinationRate,    bad: true },
                  { label: "Regression Pass Rate", value: card.regressionPassRate,   bad: false },
                ].map(({ label, value, bad }) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-slate-500">{label}</span>
                    <span
                      className={`font-semibold tabular-nums ${
                        bad && value > 0
                          ? "text-red-600"
                          : !bad && value >= 0.9
                          ? "text-emerald-600"
                          : "text-slate-700"
                      }`}
                    >
                      {(value * 100).toFixed(1)}%
                    </span>
                  </div>
                ))}

                <div className="flex justify-between">
                  <span className="text-slate-500">Latency p50</span>
                  <span className="font-semibold tabular-nums text-slate-700">
                    {card.latencyP50Ms}ms
                  </span>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        );
      })}
    </div>
  );
}
```

---

### 7.3 Recharts Grouped Bar Chart (Baseline vs Candidate)

```tsx
// components/experiments/eval-bar-chart.tsx
"use client";

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

interface EvalBarDatum {
  eval: string;
  baseline: number;
  candidate: number;
}

export function EvalBarChart({ data }: { data: EvalBarDatum[] }) {
  return (
    <Card>
      <CardHeader>
        <h3 className="text-sm font-semibold text-slate-700">
          Per-Evaluator Score Comparison
        </h3>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart
            data={data}
            margin={{ top: 4, right: 16, left: 0, bottom: 0 }}
            barCategoryGap="25%"
            barGap={3}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
            <XAxis
              dataKey="eval"
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
              tick={{ fontSize: 10, fill: "#94a3b8" }}
              axisLine={false}
              tickLine={false}
              domain={[0, 1]}
            />
            <Tooltip
              contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
              formatter={(value: number) => `${(value * 100).toFixed(1)}%`}
            />
            <Legend
              wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
            />
            <Bar
              dataKey="baseline"
              name="Baseline"
              fill="#94a3b8"
              radius={[3, 3, 0, 0]}
              isAnimationActive={true}
              animationDuration={700}
              animationEasing="ease-out"
            />
            <Bar
              dataKey="candidate"
              name="Candidate"
              fill="#10b981"
              radius={[3, 3, 0, 0]}
              isAnimationActive={true}
              animationDuration={700}
              animationBegin={100}
              animationEasing="ease-out"
            />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
```

---

### 7.4 Verdict Badge with Scale-Up Animation

```tsx
// components/experiments/verdict-badge.tsx
"use client";

import { motion } from "motion/react";
import { CheckCircle2, XCircle, Clock, ShieldAlert } from "lucide-react";

type Verdict = "promoted" | "rejected" | "pending_human_review" | "blocked_critical_failure";

const verdictConfig: Record<Verdict, {
  label: string;
  icon: typeof CheckCircle2;
  className: string;
}> = {
  promoted:                { label: "Promoted",               icon: CheckCircle2, className: "border-emerald-300 bg-emerald-100 text-emerald-800" },
  rejected:                { label: "Rejected",               icon: XCircle,      className: "border-red-300 bg-red-100 text-red-800" },
  pending_human_review:    { label: "Pending Human Review",   icon: Clock,        className: "border-amber-300 bg-amber-100 text-amber-800" },
  blocked_critical_failure:{ label: "Blocked — Critical",     icon: ShieldAlert,  className: "border-red-400 bg-red-100 text-red-900" },
};

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const config = verdictConfig[verdict];
  const Icon = config.icon;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.6 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{
        type: "spring",
        stiffness: 350,
        damping: 18,
        delay: 0.3,
      }}
      className="flex justify-center"
    >
      <span
        className={`inline-flex items-center gap-2 rounded-full border px-5 py-2 text-sm font-semibold ${config.className}`}
      >
        <Icon size={16} />
        {config.label}
      </span>
    </motion.div>
  );
}
```

---

## 8. Release Gate

### 8.1 Component Composition

```
PageTransition
└── div.grid.grid-cols-3.gap-4
    ├── div.col-span-2
    │   ├── ScoreGauge          ← Recharts RadialBarChart semicircle
    │   ├── GateCriteriaChecklist ← sequential check animations
    │   └── Card (Approval history table)
    └── div.col-span-1
        ├── HumanApprovalCard   ← Textarea + Button
        └── DeploymentStatus    ← celebration animation on promote
```

---

### 8.2 Score Gauge (Semicircular, Animated Fill)

```tsx
// components/release-gate/score-gauge.tsx
"use client";

import { RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer } from "recharts";
import { Card, CardContent } from "@/components/ui/card";

interface ScoreGaugeProps {
  score: number;        // 0.0 to 1.0
  threshold?: number;   // e.g. 0.75
}

// Thresholds for color
function gaugeColor(score: number): string {
  if (score >= 0.75) return "#10b981"; // emerald
  if (score >= 0.5)  return "#f97316"; // orange
  return "#ef4444";                     // red
}

export function ScoreGauge({ score, threshold = 0.75 }: ScoreGaugeProps) {
  const pct = Math.round(score * 100);
  const color = gaugeColor(score);

  // RadialBarChart with startAngle=180, endAngle=0 creates a semicircle
  const data = [{ value: pct, fill: color }];

  return (
    <Card>
      <CardContent className="flex flex-col items-center pt-4 pb-2">
        <div className="relative h-44 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <RadialBarChart
              cx="50%"
              cy="80%"
              innerRadius="65%"
              outerRadius="90%"
              barSize={18}
              data={data}
              startAngle={180}
              endAngle={0}
            >
              {/* Background track */}
              <RadialBar
                background={{ fill: "#f1f5f9" }}
                dataKey="value"
                cornerRadius={8}
                isAnimationActive={true}
                animationDuration={900}
                animationEasing="ease-out"
              />
              <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
            </RadialBarChart>
          </ResponsiveContainer>

          {/* Center label */}
          <div className="absolute bottom-4 left-0 right-0 flex flex-col items-center">
            <span className="text-3xl font-bold tabular-nums" style={{ color }}>
              {pct}%
            </span>
            <span className="text-xs text-slate-400">Release Score</span>
          </div>
        </div>

        <p className="mt-1 text-xs text-slate-400">
          Threshold: {Math.round(threshold * 100)}% — score must exceed for auto-promote
        </p>
      </CardContent>
    </Card>
  );
}
```

---

### 8.3 Gate Criteria Checklist with Sequential Check Animations

```tsx
// components/release-gate/gate-checklist.tsx
"use client";

import { motion } from "motion/react";
import { CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

interface GateCriterion {
  id: string;
  label: string;
  actual: string;
  threshold: string;
  passed: boolean;
}

export function GateCriteriaChecklist({ criteria }: { criteria: GateCriterion[] }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <h3 className="text-sm font-semibold text-slate-700">Promotion Rules</h3>
        <p className="text-xs text-slate-400">All 6 must pass for automatic promotion</p>
      </CardHeader>
      <CardContent className="space-y-2">
        {criteria.map((criterion, i) => (
          <motion.div
            key={criterion.id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{
              delay: i * 0.1,           // sequential reveal
              duration: 0.2,
              ease: "easeOut",
            }}
            className="flex items-center gap-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2"
          >
            {/* Animated icon */}
            <motion.div
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{
                delay: i * 0.1 + 0.15,
                type: "spring",
                stiffness: 400,
                damping: 15,
              }}
            >
              {criterion.passed ? (
                <CheckCircle2 size={16} className="text-emerald-500" />
              ) : (
                <XCircle size={16} className="text-red-500" />
              )}
            </motion.div>

            <span className="flex-1 text-xs text-slate-700">{criterion.label}</span>

            <div className="text-right text-xs tabular-nums">
              <span
                className={`font-semibold ${
                  criterion.passed ? "text-emerald-600" : "text-red-600"
                }`}
              >
                {criterion.actual}
              </span>
              <span className="text-slate-400"> / {criterion.threshold}</span>
            </div>
          </motion.div>
        ))}
      </CardContent>
    </Card>
  );
}
```

---

### 8.4 Human Approval Card

**shadcn/ui components:** `Card`, `Textarea`, `Button`, `Avatar`, `AvatarFallback`, `Badge`

```tsx
// components/release-gate/approval-card.tsx
"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { CheckCircle2, XCircle } from "lucide-react";

interface ApprovalCardProps {
  reviewerName: string;
  reviewerInitials: string;
  status: "pending" | "approved" | "rejected";
  onApprove: (comment: string) => void;
  onReject: (comment: string) => void;
}

export function ApprovalCard({
  reviewerName,
  reviewerInitials,
  status,
  onApprove,
  onReject,
}: ApprovalCardProps) {
  const [comment, setComment] = useState("");

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <Avatar className="h-7 w-7">
            <AvatarFallback className="text-xs">{reviewerInitials}</AvatarFallback>
          </Avatar>
          <div>
            <p className="text-sm font-medium text-slate-800">{reviewerName}</p>
            <p className="text-xs text-slate-400">Reviewer</p>
          </div>
          <div className="ml-auto">
            <Badge
              variant="outline"
              className={
                status === "approved"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : status === "rejected"
                  ? "border-red-200 bg-red-50 text-red-700"
                  : "border-amber-200 bg-amber-50 text-amber-700"
              }
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <AnimatePresence mode="wait">
          {status === "pending" ? (
            <motion.div
              key="form"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="space-y-3"
            >
              <Textarea
                placeholder="Optional comment for audit trail…"
                className="h-20 resize-none text-sm"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
              <div className="flex gap-2">
                <Button
                  onClick={() => onApprove(comment)}
                  size="sm"
                  className="flex-1 gap-1 bg-emerald-600 hover:bg-emerald-700"
                >
                  <CheckCircle2 size={13} />
                  Approve & Promote
                </Button>
                <Button
                  onClick={() => onReject(comment)}
                  size="sm"
                  variant="outline"
                  className="flex-1 gap-1 border-red-200 text-red-600 hover:bg-red-50"
                >
                  <XCircle size={13} />
                  Reject
                </Button>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="result"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ type: "spring", stiffness: 300, damping: 20 }}
              className="rounded-lg border border-slate-100 bg-slate-50 p-3 text-xs text-slate-600"
            >
              {comment || "No comment provided."}
            </motion.div>
          )}
        </AnimatePresence>
      </CardContent>
    </Card>
  );
}
```

---

### 8.5 Deployment Status with Celebration Animation

```tsx
// components/release-gate/deployment-status.tsx
"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Rocket, Package, CheckCheck } from "lucide-react";

type DeployStage = "idle" | "tagging" | "promoting" | "complete";

interface ParticleProps {
  id: number;
}

function Particle({ id }: ParticleProps) {
  const x = (Math.random() - 0.5) * 200;
  const y = -Math.random() * 180;
  const color = ["#10b981", "#f97316", "#6366f1", "#f59e0b"][id % 4];

  return (
    <motion.span
      className="absolute h-2 w-2 rounded-full"
      style={{ background: color, left: "50%", top: "50%" }}
      initial={{ x: 0, y: 0, opacity: 1, scale: 1 }}
      animate={{ x, y, opacity: 0, scale: 0 }}
      transition={{ duration: 0.9 + Math.random() * 0.5, ease: "easeOut" }}
    />
  );
}

export function DeploymentStatus({ stage }: { stage: DeployStage }) {
  const [particles, setParticles] = useState<number[]>([]);

  useEffect(() => {
    if (stage === "complete") {
      setParticles(Array.from({ length: 18 }, (_, i) => i));
      const timer = setTimeout(() => setParticles([]), 1400);
      return () => clearTimeout(timer);
    }
  }, [stage]);

  const stageConfig = {
    idle:      { label: "Awaiting approval",  icon: Package,   color: "text-slate-400" },
    tagging:   { label: "Tagging candidate…", icon: Package,   color: "text-amber-500" },
    promoting: { label: "Promoting to prod…", icon: Rocket,    color: "text-violet-500" },
    complete:  { label: "Deployed!",           icon: CheckCheck, color: "text-emerald-500" },
  };

  const config = stageConfig[stage];
  const Icon = config.icon;

  return (
    <div className="relative flex flex-col items-center gap-2 py-4">
      {/* Confetti particles */}
      <AnimatePresence>
        {particles.map((id) => (
          <Particle key={id} id={id} />
        ))}
      </AnimatePresence>

      <motion.div
        key={stage}
        initial={{ scale: 0.7, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 380, damping: 18 }}
      >
        <Icon size={28} className={config.color} />
      </motion.div>

      <motion.p
        key={`${stage}-label`}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className={`text-sm font-medium ${config.color}`}
      >
        {config.label}
      </motion.p>
    </div>
  );
}
```

---

## Quick Reference: Import Paths

```tsx
// Framer Motion (v11 — use motion/react, not framer-motion directly)
import { motion, AnimatePresence, useMotionValue, useTransform, animate } from "motion/react";

// shadcn/ui
import { Button }           from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge }            from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Separator }        from "@/components/ui/separator";
import { ScrollArea }       from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input }            from "@/components/ui/input";
import { Textarea }         from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Progress }         from "@/components/ui/progress";
import { Skeleton }         from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

// Recharts
import { AreaChart, Area, BarChart, Bar, RadialBarChart, RadialBar,
         XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine,
         ResponsiveContainer, PolarAngleAxis } from "recharts";

// Lucide
import { Home, MessageSquare, Activity, TrendingDown,
         Lightbulb, FlaskConical, ShieldCheck, Settings,
         Wrench, CheckCircle2, XCircle, ChevronRight,
         ChevronDown, ExternalLink, Rocket, AlertTriangle,
         Stethoscope, Package, CheckCheck, Zap } from "lucide-react";
```

---

## Animation Constants (copy to `lib/motion.ts`)

```ts
// lib/motion.ts

// Page-level transitions
export const pageTransition = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit:    { opacity: 0, y: -4 },
  transition: { duration: 0.18, ease: [0.25, 0.1, 0.25, 1.0] as const },
};

// Standard stagger container
export const staggerContainer = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.06,
      delayChildren: 0.08,
    },
  },
};

// Standard stagger item (fade up)
export const staggerItem = {
  hidden: { opacity: 0, y: 10 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.22 } },
};

// Spring presets
export const springSnappy   = { type: "spring", stiffness: 380, damping: 26 } as const;
export const springGentle   = { type: "spring", stiffness: 220, damping: 30 } as const;
export const springBouncy   = { type: "spring", stiffness: 340, damping: 18 } as const;

// Sidebar active pill
export const sidebarPillTransition = {
  type: "spring",
  stiffness: 400,
  damping: 35,
} as const;
```

---

*Sources consulted:*
- [Framer Motion — React Animation Docs](https://www.framer.com/motion/animation/)
- [Motion.dev — useAnimate](https://motion.dev/docs/react-use-animate)
- [Motion.dev — AnimatePresence](https://motion.dev/docs/react-animate-presence)
- [Framer Motion — Stagger](https://www.framer.com/motion/stagger/)
- [Recharts API Docs](https://recharts.github.io/en-US/api/)
- [shadcn/ui Dashboard Examples](https://ui.shadcn.com/examples/dashboard)
- [shadcn/ui Radial Charts](https://ui.shadcn.com/charts/radial)
