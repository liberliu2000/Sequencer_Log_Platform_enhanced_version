import type { InputHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type SwitchProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

export function Switch({ className, ...props }: SwitchProps) {
  return (
    <label className={cn("relative inline-flex cursor-pointer items-center", className)}>
      <input {...props} type="checkbox" className="peer sr-only" />
      <span className="h-6 w-11 rounded-full bg-[var(--border)] transition peer-checked:bg-[var(--accent)]" />
      <span className="absolute left-1 h-4 w-4 rounded-full bg-white transition peer-checked:translate-x-5" />
    </label>
  );
}
