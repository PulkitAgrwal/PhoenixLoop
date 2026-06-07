import * as React from "react";
import { cn } from "@/lib/utils";

export type TagTone = "default" | "brand" | "fail" | "warn" | "mute";

const toneClasses: Record<TagTone, string> = {
  default: "border-hairline text-ink",
  brand: "border-brand/50 text-brand-soft",
  fail: "border-fail/50 text-fail",
  warn: "border-warn/50 text-warn",
  mute: "border-hairline text-mute",
};

export interface TagProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: TagTone;
}

export const Tag = React.forwardRef<HTMLSpanElement, TagProps>(
  ({ tone = "default", className, children, ...props }, ref) => (
    <span
      ref={ref}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-pill border bg-canvas px-3 py-0.5 text-body-sm leading-5",
        toneClasses[tone],
        className
      )}
      {...props}
    >
      {children}
    </span>
  )
);
Tag.displayName = "Tag";
