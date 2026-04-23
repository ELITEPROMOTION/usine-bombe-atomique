import { ReactNode } from "react";
import clsx from "clsx";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { Status } from "./tokens";

export interface KPIWidgetProps {
  icon?: ReactNode;
  label: string;
  value: ReactNode;
  delta?: number;
  deltaLabel?: string;
  sparkline?: number[];
  status?: Status;
  hint?: string;
  loading?: boolean;
}

export function KPIWidget({
  icon, label, value, delta, deltaLabel, sparkline, status, hint, loading,
}: KPIWidgetProps) {
  const trendIcon =
    delta === undefined ? null
      : delta > 0 ? <TrendingUp size={12} className="text-emerald-400" />
      : delta < 0 ? <TrendingDown size={12} className="text-red-400" />
      : <Minus size={12} className="text-ink-400" />;

  const statusRing = status === "error" ? "ring-red-500/20"
    : status === "warning" ? "ring-yellow-500/20"
    : status === "success" ? "ring-emerald-500/20"
    : "ring-ink-700/40";

  return (
    <div
      className={clsx(
        "rounded-lg border border-ink-800/80 bg-ink-900/60 p-4 ring-1 ring-offset-0",
        "backdrop-blur-sm transition-all hover:border-ink-700 hover:shadow-panel",
        statusRing,
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.14em] text-ink-300">
          {icon && <span className="text-ink-300">{icon}</span>}
          <span>{label}</span>
        </div>
        {sparkline && sparkline.length > 1 && <Sparkline values={sparkline} />}
      </div>
      <div className={clsx("font-display text-2xl font-semibold text-ink-50",
                           loading && "animate-pulse")}>
        {loading ? "—" : value}
      </div>
      {(delta !== undefined || deltaLabel) && (
        <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-ink-400">
          {trendIcon}
          <span>
            {delta !== undefined && (
              <span className={clsx(
                "font-medium",
                delta > 0 && "text-emerald-300",
                delta < 0 && "text-red-300",
              )}>
                {delta > 0 ? "+" : ""}{delta.toFixed(1)}%
              </span>
            )}
            {deltaLabel && <span className="ml-1">{deltaLabel}</span>}
          </span>
        </div>
      )}
      {hint && !deltaLabel && <div className="mt-1 text-[11px] text-ink-400">{hint}</div>}
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const w = 48, h = 16;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg width={w} height={h} className="text-gold-400/70">
      <polyline
        points={points} fill="none" stroke="currentColor"
        strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
      />
    </svg>
  );
}
