import { ReactNode } from "react";
import clsx from "clsx";
import type { Status } from "./tokens";

export interface BadgeProps {
  status?: Status;
  children: ReactNode;
  size?: "sm" | "md";
}

const STATUS_CLASSES: Record<Status, string> = {
  success: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  warning: "bg-yellow-500/10 text-yellow-200 border-yellow-500/30",
  error:   "bg-red-500/10 text-red-300 border-red-500/30",
  info:    "bg-blue-500/10 text-blue-300 border-blue-500/30",
  neutral: "bg-ink-700/40 text-ink-200 border-ink-600/50",
};

export function Badge({ status = "neutral", children, size = "md" }: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full border font-medium whitespace-nowrap",
        STATUS_CLASSES[status],
        size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-xs",
      )}
    >
      {children}
    </span>
  );
}
