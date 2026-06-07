import * as React from "react";
import { cn } from "@/lib/utils";

export const CodeInline = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(
  ({ className, children, ...props }, ref) => (
    <code
      ref={ref}
      className={cn(
        "inline-flex items-center rounded-xs bg-canvas-soft px-1.5 py-[1px] font-mono text-[12.5px] leading-[18px] text-canvas-text-soft",
        className
      )}
      {...props}
    >
      {children}
    </code>
  )
);
CodeInline.displayName = "CodeInline";
