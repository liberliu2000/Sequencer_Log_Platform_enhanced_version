import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-xl text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-transparent",
  {
    variants: {
      variant: {
        default:
          "bg-[linear-gradient(135deg,var(--accent),var(--accent-strong))] text-[var(--accent-foreground)] shadow-[0_12px_28px_-18px_rgba(18,76,165,0.58)] hover:brightness-105",
        secondary:
          "border border-[rgba(126,184,255,0.22)] bg-[linear-gradient(180deg,rgba(255,255,255,0.84),rgba(237,245,255,0.78))] text-[var(--foreground)] hover:bg-[rgba(223,234,251,0.92)] dark:bg-[rgba(12,27,45,0.82)]",
        ghost: "text-[var(--muted-foreground)] hover:bg-[rgba(223,234,251,0.72)] hover:text-[var(--foreground)]",
        danger: "bg-[var(--danger)] text-white hover:bg-[#b53037]",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 px-3",
        lg: "h-11 px-5 text-base",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
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
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
