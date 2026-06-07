import * as React from "react";
import { cn } from "@/lib/utils";

export interface HairlineDividerProps extends React.HTMLAttributes<HTMLDivElement> {
  orientation?: "horizontal" | "vertical";
  dashed?: boolean;
  brand?: boolean;
}

export function HairlineDivider({
  orientation = "horizontal",
  dashed = false,
  brand = false,
  className,
  ...rest
}: HairlineDividerProps) {
  const isH = orientation === "horizontal";
  return (
    <div
      role="separator"
      aria-orientation={orientation}
      className={cn(
        isH ? "h-px w-full" : "w-px h-full",
        brand
          ? isH
            ? "bg-brand"
            : "bg-brand"
          : "bg-hairline",
        dashed && "bg-transparent",
        dashed && isH && "border-t border-dashed border-hairline",
        dashed && !isH && "border-l border-dashed border-hairline",
        className
      )}
      {...rest}
    />
  );
}
