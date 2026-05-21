"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  MessageSquare,
  Activity,
  AlertTriangle,
  Wrench,
  FlaskConical,
  ShieldCheck,
  Settings,
  Menu,
  Flame,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";

const navItems = [
  { href: "/", label: "Home", icon: LayoutDashboard },
  { href: "/conversation", label: "Conversation", icon: MessageSquare },
  { href: "/traces", label: "Traces & Evals", icon: Activity },
  { href: "/failures", label: "Failure Trends", icon: AlertTriangle },
  { href: "/improvements", label: "Improvements", icon: Wrench },
  { href: "/experiments", label: "Experiments", icon: FlaskConical },
  { href: "/release-gate", label: "Release Gate", icon: ShieldCheck },
  { href: "/settings", label: "Settings", icon: Settings },
];

interface NavItemProps {
  href: string;
  label: string;
  icon: React.ElementType;
  isActive: boolean;
  onClick?: () => void;
}

function NavItem({ href, label, icon: Icon, isActive, onClick }: NavItemProps) {
  return (
    <Link href={href} onClick={onClick}>
      <div
        className={cn(
          "group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-all duration-150",
          isActive
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
        )}
      >
        <Icon
          className={cn(
            "h-4 w-4 shrink-0 transition-transform duration-150 group-hover:scale-110",
            isActive && "text-primary"
          )}
        />
        <span>{label}</span>
      </div>
    </Link>
  );
}

function SidebarLogo() {
  return (
    <div className="flex items-center gap-2 px-3 py-4">
      <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary">
        <Flame className="h-5 w-5 text-primary-foreground" />
      </div>
      <span className="text-lg font-bold tracking-tight">PhoenixLoop</span>
    </div>
  );
}

function SidebarNav({
  pathname,
  onNavClick,
}: {
  pathname: string;
  onNavClick?: () => void;
}) {
  return (
    <nav className="flex flex-col gap-1 px-2">
      {navItems.map((item) => (
        <NavItem
          key={item.href}
          href={item.href}
          label={item.label}
          icon={item.icon}
          isActive={
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href)
          }
          onClick={onNavClick}
        />
      ))}
    </nav>
  );
}

function DesktopSidebar({ pathname }: { pathname: string }) {
  return (
    <aside className="hidden w-60 shrink-0 border-r bg-background md:flex md:flex-col">
      <SidebarLogo />
      <div className="border-t pt-3">
        <SidebarNav pathname={pathname} />
      </div>
    </aside>
  );
}

function MobileSidebar({ pathname }: { pathname: string }) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="fixed left-4 top-4 z-40 md:hidden"
          aria-label="Open navigation menu"
        >
          <Menu className="h-5 w-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-60 p-0">
        <SidebarLogo />
        <div className="border-t pt-3">
          <SidebarNav pathname={pathname} />
        </div>
      </SheetContent>
    </Sheet>
  );
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <>
      <DesktopSidebar pathname={pathname} />
      <MobileSidebar pathname={pathname} />
    </>
  );
}
