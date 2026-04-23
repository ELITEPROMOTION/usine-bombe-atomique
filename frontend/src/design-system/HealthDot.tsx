import clsx from "clsx";
import type { Status } from "./tokens";

export interface HealthDotProps {
  status: Status;
  animated?: boolean;
  size?: "sm" | "md" | "lg";
  label?: string;
}

const STATUS_BG: Record<Status, string> = {
  success: "bg-emerald-400",
  warning: "bg-yellow-400",
  error:   "bg-red-400",
  info:    "bg-blue-400",
  neutral: "bg-ink-400",
};

export function HealthDot({
  status, animated = false, size = "md", label,
}: HealthDotProps) {
  const dim = size === "sm" ? "w-2 h-2" : size === "lg" ? "w-3.5 h-3.5" : "w-2.5 h-2.5";
  return (
    <span className="inline-flex items-center gap-2">
      <span className="relative inline-flex">
        {animated && (
          <span
            className={clsx(
              "absolute inset-0 rounded-full opacity-60",
              STATUS_BG[status],
              "animate-ping",
            )}
          />
        )}
        <span className={clsx("relative rounded-full", STATUS_BG[status], dim)} />
      </span>
      {label && <span className="text-xs text-ink-200">{label}</span>}
    </span>
  );
}
