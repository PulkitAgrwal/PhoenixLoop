import * as React from "react";
import { cn } from "@/lib/utils";

export interface GridOverlayProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "grid" | "dot";
  fade?: "none" | "radial" | "top" | "bottom";
}

export function GridOverlay({
  variant = "grid",
  fade = "radial",
  className,
  ...rest
}: GridOverlayProps) {
  const fadeStyle: React.CSSProperties =
    fade === "radial"
      ? {
          maskImage:
            "radial-gradient(ellipse 60% 50% at 50% 35%, black 30%, transparent 80%)",
          WebkitMaskImage:
            "radial-gradient(ellipse 60% 50% at 50% 35%, black 30%, transparent 80%)",
        }
      : fade === "top"
      ? {
          maskImage: "linear-gradient(to bottom, black 0%, transparent 80%)",
          WebkitMaskImage: "linear-gradient(to bottom, black 0%, transparent 80%)",
        }
      : fade === "bottom"
      ? {
          maskImage: "linear-gradient(to top, black 0%, transparent 80%)",
          WebkitMaskImage: "linear-gradient(to top, black 0%, transparent 80%)",
        }
      : {};

  return (
    <div
      aria-hidden="true"
      className={cn(
        "pointer-events-none absolute inset-0",
        variant === "grid" ? "grid-overlay" : "dot-overlay",
        className
      )}
      style={fadeStyle}
      {...rest}
    />
  );
}
