import { PageHeader } from "@/components/layout/page-header";
import { PageTabs } from "@/components/layout/page-tabs";

const HEALING_TABS = [
  { href: "/healing/improvements", label: "Improvements" },
  { href: "/healing/experiments", label: "Experiments" },
  { href: "/healing/release-gate", label: "Release Gate" },
];

export default function HealingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Healing"
        description="Diagnose failures, run experiments, and gate releases"
      />
      <PageTabs tabs={HEALING_TABS} />
      <div>{children}</div>
    </div>
  );
}
