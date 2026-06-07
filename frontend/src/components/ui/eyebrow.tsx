import * as React from "react";
import { cn } from "@/lib/utils";

export interface EyebrowProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: "default" | "brand" | "mute";
}

export const Eyebrow = React.forwardRef<HTMLSpanElement, EyebrowProps>(
  ({ tone = "default", className, children, ...props }, ref) => (
    <span
      ref={ref}
      className={cn(
        "inline-block uppercase text-eyebrow-mono",
        tone === "brand" && "text-brand-soft",
        tone === "mute" && "text-mute",
        tone === "default" && "text-body",
        className
      )}
      {...props}
    >
      {children}
    </span>
  )
);
Eyebrow.displayName = "Eyebrow";
