import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { TopNav } from "@/components/layout/top-nav";
import { HealingCycleProvider } from "@/components/healing/healing-cycle-context";
import { HealingCycleModal } from "@/components/healing/healing-cycle-modal";
import { HealingCycleChip } from "@/components/healing/healing-cycle-chip";
import { DismissWarningDialog } from "@/components/healing/dismiss-warning-dialog";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "PhoenixLoop — agents that observe and rewrite themselves",
  description:
    "A Gemini support agent that traces every run with Arize Phoenix, clusters its own failures, drafts a prompt fix, A/B-tests it, and gates promotion on the score.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen bg-canvas text-ink antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-sm focus:bg-brand focus:px-3 focus:py-2 focus:text-on-brand focus:font-semibold"
        >
          Skip to content
        </a>
        <HealingCycleProvider>
          <TopNav />
          <main id="main" className="min-h-[calc(100vh-56px)]">
            {children}
          </main>
          <HealingCycleModal />
          <HealingCycleChip />
          <DismissWarningDialog />
        </HealingCycleProvider>
      </body>
    </html>
  );
}
