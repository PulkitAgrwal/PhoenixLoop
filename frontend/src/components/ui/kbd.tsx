import * as React from "react";
import { cn } from "@/lib/utils";

export const KBD = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(
  ({ className, children, ...props }, ref) => (
    <kbd
      ref={ref}
      className={cn(
        "inline-flex h-5 min-w-[20px] items-center justify-center rounded-xs border border-hairline bg-canvas-soft px-1.5 text-[11px] leading-none text-body",
        className
      )}
      {...props}
    >
      {children}
    </kbd>
  )
);
KBD.displayName = "KBD";
