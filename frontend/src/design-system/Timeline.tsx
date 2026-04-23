import { ReactNode } from "react";
import clsx from "clsx";
import type { Status } from "./tokens";

export interface TimelineItem {
  id: string;
  title: ReactNode;
  description?: ReactNode;
  time: string;
  status?: Status;
  icon?: ReactNode;
  badges?: ReactNode;
}

export interface TimelineProps {
  items: TimelineItem[];
  compact?: boolean;
}

const STATUS_COLOR: Record<Status, string> = {
  success: "bg-emerald-500",
  warning: "bg-yellow-500",
  error:   "bg-red-500",
  info:    "bg-blue-500",
  neutral: "bg-ink-500",
};

export function Timeline({ items, compact }: TimelineProps) {
  if (!items.length) {
    return (
      <div className="text-xs text-ink-400 italic py-6 text-center">
        Aucun evenement.
      </div>
    );
  }
  return (
    <ol className="relative border-l border-ink-700/60 ml-2 space-y-3">
      {items.map((it) => (
        <li key={it.id} className="relative pl-5">
          <span
            className={clsx(
              "absolute -left-[5px] top-1 rounded-full ring-2 ring-ink-900",
              "w-2.5 h-2.5",
              STATUS_COLOR[it.status ?? "neutral"],
            )}
          />
          <div className={clsx("flex items-start justify-between gap-3",
                               compact ? "text-xs" : "text-sm")}>
            <div className="min-w-0 flex-1">
              <div className="text-ink-100 font-medium flex items-center gap-2">
                {it.icon && <span>{it.icon}</span>}
                <span className="truncate">{it.title}</span>
                {it.badges}
              </div>
              {it.description && (
                <div className="text-ink-400 mt-0.5 text-xs truncate">
                  {it.description}
                </div>
              )}
            </div>
            <div className="text-[10px] text-ink-500 whitespace-nowrap mt-0.5">
              {it.time}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
