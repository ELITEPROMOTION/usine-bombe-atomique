import clsx from "clsx";

interface ScoreRingProps {
  score: number;
  size?: number;
  label?: string;
  className?: string;
}

export function ScoreRing({ score, size = 104, label, className }: ScoreRingProps) {
  const clamped = Math.max(0, Math.min(1, score));
  const r = (size - 10) / 2;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - clamped);
  const pct = (clamped * 100).toFixed(1);

  return (
    <div className={clsx("relative inline-flex items-center justify-center", className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <defs>
          <linearGradient id="score-g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#f1d98c" />
            <stop offset="100%" stopColor="#c49129" />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="#1c1c22" strokeWidth={6} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke="url(#score-g)"
          strokeWidth={6}
          fill="none"
          strokeDasharray={c}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 700ms cubic-bezier(.2,.8,.2,1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-2xl font-semibold text-ink-50 tabular-nums">{pct}<span className="text-ink-400 text-sm">%</span></div>
        {label && <div className="text-[10px] uppercase tracking-[0.18em] text-ink-400 mt-0.5">{label}</div>}
      </div>
    </div>
  );
}
