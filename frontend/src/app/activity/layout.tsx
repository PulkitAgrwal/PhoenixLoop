import { PageHeader } from "@/components/layout/page-header";
import { PageTabs } from "@/components/layout/page-tabs";

const ACTIVITY_TABS = [
  { href: "/activity/runs", label: "Runs" },
  { href: "/activity/failures", label: "Failure Trends" },
];

export default function ActivityLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Activity"
        description="Agent runs and failure patterns from production traffic"
      />
      <PageTabs tabs={ACTIVITY_TABS} />
      <div>{children}</div>
    </div>
  );
}
