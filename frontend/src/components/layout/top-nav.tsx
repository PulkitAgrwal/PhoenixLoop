"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { StatusDot } from "@/components/ui/status-dot";

type NavItem = { href: string; label: string; sub?: { href: string; label: string }[] };

const PRIMARY_NAV: NavItem[] = [
  { href: "/", label: "Overview" },
  { href: "/conversation", label: "Conversation" },
  {
    href: "/activity",
    label: "Activity",
    sub: [
      { href: "/activity/runs", label: "Runs" },
      { href: "/activity/failures", label: "Failures" },
    ],
  },
  {
    href: "/healing",
    label: "Healing",
    sub: [
      { href: "/healing/improvements", label: "Improvements" },
      { href: "/healing/experiments", label: "Experiments" },
      { href: "/healing/release-gate", label: "Release gate" },
    ],
  },
  { href: "/prompts", label: "Prompts" },
  { href: "/settings", label: "Settings" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

export function TopNav() {
  const pathname = usePathname();
  const [open, setOpen] = React.useState(false);
  const active = PRIMARY_NAV.find((n) => isActive(pathname, n.href));
  const showSub = !!active?.sub;

  return (
    <header className="sticky top-0 z-40 bg-canvas/95 backdrop-blur-[2px] border-b border-hairline">
      <div className="mx-auto flex h-14 max-w-[1280px] items-center justify-between px-5 lg:px-8">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2 group" aria-label="PhoenixLoop home">
            <span className="relative inline-flex h-6 w-6 items-center justify-center">
              <span className="absolute inset-0 rounded-sm border border-brand/40" />
              <span className="absolute inset-[3px] rounded-[2px] bg-brand" />
            </span>
            <span className="text-body-md font-semibold tracking-tightish text-ink-strong">
              PhoenixLoop
            </span>
          </Link>

          <nav aria-label="Primary" className="hidden md:flex items-center gap-1">
            {PRIMARY_NAV.map((item) => {
              const on = isActive(pathname, item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "px-3 py-1.5 text-body-sm rounded-sm transition-colors",
                    on ? "text-ink-strong" : "text-body hover:text-ink"
                  )}
                  aria-current={on ? "page" : undefined}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          <a
            href="https://github.com"
            target="_blank"
            rel="noreferrer noopener"
            className="hidden md:inline-flex items-center gap-2 px-3 py-1.5 text-body-sm text-body hover:text-ink rounded-sm border border-hairline"
          >
            <StatusDot tone="brand" size="xs" pulse />
            <span>Local · live mode</span>
          </a>
          <button
            type="button"
            className="md:hidden inline-flex h-9 w-9 items-center justify-center rounded-sm border border-hairline text-ink"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {showSub && (
        <div className="hidden md:block border-t border-hairline bg-canvas">
          <nav
            aria-label={`${active!.label} sections`}
            className="mx-auto flex max-w-[1280px] items-center gap-5 px-5 lg:px-8"
          >
            {active!.sub!.map((s) => {
              const on = isActive(pathname, s.href);
              return (
                <Link
                  key={s.href}
                  href={s.href}
                  className={cn(
                    "relative py-3 text-body-sm transition-colors",
                    on ? "text-ink-strong" : "text-body hover:text-ink"
                  )}
                  aria-current={on ? "page" : undefined}
                >
                  {s.label}
                  {on && (
                    <span className="absolute -bottom-px left-0 right-0 h-[2px] bg-brand" />
                  )}
                </Link>
              );
            })}
          </nav>
        </div>
      )}

      {open && (
        <div className="md:hidden border-t border-hairline bg-canvas">
          <nav aria-label="Mobile" className="flex flex-col px-5 py-3">
            {PRIMARY_NAV.map((item) => {
              const on = isActive(pathname, item.href);
              return (
                <React.Fragment key={item.href}>
                  <Link
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "py-2 text-body-md",
                      on ? "text-ink-strong" : "text-body"
                    )}
                  >
                    {item.label}
                  </Link>
                  {item.sub && on && (
                    <div className="ml-3 mb-2 flex flex-col">
                      {item.sub.map((s) => (
                        <Link
                          key={s.href}
                          href={s.href}
                          onClick={() => setOpen(false)}
                          className={cn(
                            "py-1.5 text-body-sm",
                            isActive(pathname, s.href) ? "text-brand-soft" : "text-mute"
                          )}
                        >
                          {s.label}
                        </Link>
                      ))}
                    </div>
                  )}
                </React.Fragment>
              );
            })}
          </nav>
        </div>
      )}
    </header>
  );
}
