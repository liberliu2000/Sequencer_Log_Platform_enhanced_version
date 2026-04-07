import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-[rgba(126,184,255,0.24)] bg-[rgba(69,128,212,0.1)] px-2.5 py-1 text-xs font-medium text-[var(--foreground)]",
        className,
      )}
      {...props}
    />
  );
}
