import { motion } from "framer-motion";

interface Props {
  /** 0..100 */
  value: number;
  label?: string;
  sublabel?: string;
  size?: "sm" | "md" | "lg";
}

const SIZES = {
  sm: { box: 96, stroke: 8, font: "text-base" },
  md: { box: 144, stroke: 10, font: "text-2xl" },
  lg: { box: 192, stroke: 12, font: "text-3xl" },
} as const;

export function ProgressGauge({ value, label, sublabel, size = "md" }: Props) {
  const { box, stroke, font } = SIZES[size];
  const r = (box - stroke) / 2;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, value));
  const offset = c * (1 - clamped / 100);

  return (
    <div className="inline-flex flex-col items-center">
      <div
        className="relative"
        style={{ width: box, height: box }}
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <svg width={box} height={box} className="-rotate-90">
          <circle
            cx={box / 2} cy={box / 2} r={r}
            stroke="rgba(106,106,121,0.25)"
            strokeWidth={stroke}
            fill="none"
          />
          <motion.circle
            cx={box / 2} cy={box / 2} r={r}
            stroke="url(#progressGoldGradient)"
            strokeWidth={stroke}
            strokeLinecap="round"
            fill="none"
            strokeDasharray={c}
            initial={{ strokeDashoffset: c }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 0.8, ease: "easeOut" }}
          />
          <defs>
            <linearGradient
              id="progressGoldGradient" x1="0" y1="0" x2="1" y2="1"
            >
              <stop offset="0%" stopColor="#f1d98c" />
              <stop offset="55%" stopColor="#e7c05b" />
              <stop offset="100%" stopColor="#c49129" />
            </linearGradient>
          </defs>
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`font-display font-semibold tabular-nums text-ink-50 ${font}`}>
            {clamped.toFixed(0)}%
          </span>
          {sublabel && (
            <span className="text-[10px] uppercase tracking-[0.2em] text-ink-300 mt-1">
              {sublabel}
            </span>
          )}
        </div>
      </div>
      {label && (
        <div className="mt-3 text-xs text-ink-300">{label}</div>
      )}
    </div>
  );
}
