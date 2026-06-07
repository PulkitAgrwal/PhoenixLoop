import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-semibold transition-colors duration-150 disabled:pointer-events-none disabled:opacity-40 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "bg-brand text-on-brand hover:bg-brand-soft focus-visible:outline-brand",
        outline:
          "bg-canvas text-ink border border-hairline hover:border-ink hover:bg-canvas-soft",
        ghost:
          "bg-transparent text-brand-soft hover:bg-canvas-soft",
        subtle:
          "bg-canvas-soft text-ink border border-hairline hover:border-ink",
        link:
          "bg-transparent text-brand-soft underline-offset-4 hover:underline px-0",
        destructive:
          "bg-transparent text-fail border border-fail/40 hover:border-fail hover:bg-fail/10",
        // legacy aliases — keep older call-sites compiling
        default:
          "bg-brand text-on-brand hover:bg-brand-soft focus-visible:outline-brand",
        secondary:
          "bg-canvas text-ink border border-hairline hover:border-ink hover:bg-canvas-soft",
      },
      size: {
        sm: "h-8 px-3 text-body-sm rounded-sm",
        md: "h-11 px-4 text-body-md rounded-sm",
        lg: "h-12 px-6 text-body-md rounded-sm",
        icon: "h-11 w-11 rounded-sm",
        "icon-sm": "h-8 w-8 rounded-sm",
        // legacy alias
        default: "h-11 px-4 text-body-md rounded-sm",
      },
    },
    defaultVariants: {
      variant: "outline",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp ref={ref} className={cn(buttonVariants({ variant, size, className }))} {...props} />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
