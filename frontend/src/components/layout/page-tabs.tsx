"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export interface PageTab {
  href: string;
  label: string;
}

interface PageTabsProps {
  tabs: PageTab[];
}

export function PageTabs({ tabs }: PageTabsProps) {
  const pathname = usePathname();

  return (
    <nav
      role="tablist"
      aria-label="Page sections"
      className="flex items-center gap-1 border-b border-border"
    >
      {tabs.map((tab) => {
        const isActive =
          pathname === tab.href || pathname.startsWith(tab.href + "/");
        return (
          <Link
            key={tab.href}
            href={tab.href}
            role="tab"
            aria-selected={isActive}
            className={cn(
              "relative -mb-px px-4 py-2 text-sm font-medium transition-colors",
              "border-b-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              isActive
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground hover:border-muted",
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
