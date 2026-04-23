import { HTMLAttributes, ReactNode } from "react";
import clsx from "clsx";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  variant?: "default" | "glass" | "outlined";
  padding?: "none" | "sm" | "md" | "lg";
}

export function Card({
  children, variant = "default", padding = "md", className, ...props
}: CardProps) {
  return (
    <div
      className={clsx(
        "rounded-xl transition-all",
        variant === "default" &&
          "bg-ink-900/60 border border-ink-800/80 shadow-panel backdrop-blur-sm",
        variant === "glass" &&
          "bg-ink-900/30 border border-ink-700/40 backdrop-blur-md",
        variant === "outlined" &&
          "bg-transparent border border-ink-700/60",
        padding === "sm" && "p-3",
        padding === "md" && "p-5",
        padding === "lg" && "p-8",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title, hint, icon, action,
}: {
  title: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2">
        {icon && <span className="text-gold-300">{icon}</span>}
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-ink-300 font-medium">
            {title}
          </div>
          {hint && <div className="text-xs text-ink-400 mt-0.5">{hint}</div>}
        </div>
      </div>
      {action && <div>{action}</div>}
    </div>
  );
}
