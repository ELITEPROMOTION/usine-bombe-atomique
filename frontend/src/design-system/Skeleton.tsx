import clsx from "clsx";

interface Props {
  className?: string;
  width?: string | number;
  height?: string | number;
  rounded?: "none" | "sm" | "md" | "lg" | "full";
}

const ROUNDED = {
  none: "rounded-none",
  sm:   "rounded",
  md:   "rounded-md",
  lg:   "rounded-lg",
  full: "rounded-full",
} as const;

export function Skeleton({
  className, width, height, rounded = "md",
}: Props) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-live="polite"
      style={{ width, height }}
      className={clsx(
        "animate-pulse",
        "bg-gradient-to-r from-ink-800/60 via-ink-700/60 to-ink-800/60",
        "bg-[length:200%_100%]",
        ROUNDED[rounded],
        className,
      )}
    />
  );
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={clsx("space-y-2", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          height="0.875rem"
          width={i === lines - 1 ? "60%" : "100%"}
        />
      ))}
    </div>
  );
}
