import { ButtonHTMLAttributes, ReactNode } from "react";
import clsx from "clsx";

export interface ActionButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md" | "lg";
  leading?: ReactNode;
  trailing?: ReactNode;
  loading?: boolean;
}

const VARIANT: Record<NonNullable<ActionButtonProps["variant"]>, string> = {
  primary: "bg-gradient-to-br from-gold-300 to-gold-500 text-ink-950 hover:from-gold-200 hover:to-gold-400 shadow-glow-gold",
  secondary: "bg-ink-800 text-ink-100 border border-ink-700/60 hover:bg-ink-700",
  danger: "bg-red-500/90 text-white hover:bg-red-500",
  ghost: "bg-transparent text-ink-200 hover:bg-ink-800/50",
};

const SIZE = {
  sm: "px-2.5 py-1 text-xs gap-1.5",
  md: "px-3.5 py-1.5 text-sm gap-2",
  lg: "px-4 py-2 text-sm gap-2",
};

export function ActionButton({
  variant = "primary", size = "md", leading, trailing, loading,
  className, children, disabled, ...props
}: ActionButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center rounded-md font-medium transition-all",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        "focus:outline-none focus:ring-2 focus:ring-gold-400/40",
        VARIANT[variant],
        SIZE[size],
        className,
      )}
    >
      {loading ? <Spinner /> : leading}
      {children && <span>{children}</span>}
      {trailing}
    </button>
  );
}

function Spinner() {
  return (
    <span className="inline-block w-3 h-3 rounded-full border-2 border-current border-r-transparent animate-spin" />
  );
}
