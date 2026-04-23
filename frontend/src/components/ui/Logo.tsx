import clsx from "clsx";

interface LogoProps {
  size?: number;
  withWordmark?: boolean;
  className?: string;
  tagline?: string;
}

/**
 * Brand mark for Tech Industrielle (Ahmed DENDANI).
 *
 * Industrial gear (outer teeth + ring) wrapping an AI neural core
 * (6 nodes + synaptic connections) with 4 cardinal I/O nodes
 * linking into the machine. Champagne-gold gradients on dark.
 */
export function Logo({
  size = 44,
  withWordmark = true,
  className,
  tagline = "Ahmed DENDANI",
}: LogoProps) {
  return (
    <div className={clsx("flex items-center gap-3 select-none", className)}>
      <MarkSVG size={size} />
      {withWordmark && (
        <div className="leading-none">
          <div className="font-display font-semibold text-ink-50 tracking-tight text-[15px]">
            Tech Industrielle
          </div>
          <div className="text-[10.5px] uppercase tracking-[0.22em] text-gold-300/80 mt-1">
            {tagline}
          </div>
        </div>
      )}
    </div>
  );
}

export function MarkSVG({ size = 64, className }: { size?: number; className?: string }) {
  const gid = "ti-gold";
  const cid = "ti-core";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      aria-label="Tech Industrielle"
      className={clsx("drop-shadow-[0_0_18px_rgba(231,192,91,0.35)]", className)}
    >
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#f1d98c" />
          <stop offset="55%" stopColor="#d9a63c" />
          <stop offset="100%" stopColor="#82581c" />
        </linearGradient>
        <radialGradient id={cid} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#fdf8ec" />
          <stop offset="100%" stopColor="#d9a63c" />
        </radialGradient>
      </defs>

      {/* Dark rounded frame */}
      <rect
        x="1" y="1" width="62" height="62" rx="14"
        fill="#0a0a0c"
        stroke={`url(#${gid})`}
        strokeWidth="1.25"
      />

      {/* External connected I/O nodes (network topology) */}
      <g fill={`url(#${gid})`}>
        <circle cx="8"  cy="32" r="1.8" />
        <circle cx="56" cy="32" r="1.8" />
        <circle cx="32" cy="8"  r="1.8" />
        <circle cx="32" cy="56" r="1.8" />
      </g>
      <g stroke={`url(#${gid})`} strokeWidth="0.6" opacity="0.55">
        <line x1="9.5" y1="32"  x2="13" y2="32" />
        <line x1="54.5" y1="32" x2="51" y2="32" />
        <line x1="32" y1="9.5"  x2="32" y2="13" />
        <line x1="32" y1="54.5" x2="32" y2="51" />
      </g>

      {/* Industrial gear centered */}
      <g transform="translate(32 32)">
        {/* 8 teeth radiating */}
        <g fill={`url(#${gid})`}>
          {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
            <g key={deg} transform={`rotate(${deg})`}>
              <rect x="-2" y="-26" width="4" height="5.2" rx="0.8" />
            </g>
          ))}
        </g>
        {/* Outer gear ring */}
        <circle cx="0" cy="0" r="21" fill="none" stroke={`url(#${gid})`} strokeWidth="1.4" />
        {/* Inner ring */}
        <circle cx="0" cy="0" r="14.5" fill="none" stroke={`url(#${gid})`} strokeWidth="0.6" opacity="0.4" />

        {/* Neural AI core: synaptic links */}
        <g stroke={`url(#${gid})`} strokeWidth="0.55" opacity="0.75" fill="none">
          <line x1="-7.5" y1="-5"  x2="-2.5" y2="0"   />
          <line x1="-2.5" y1="0"   x2="-8"   y2="5.5" />
          <line x1="7.5"  y1="-5"  x2="2.5"  y2="0"   />
          <line x1="2.5"  y1="0"   x2="8"    y2="5.5" />
          <line x1="-2.5" y1="0"   x2="2.5"  y2="0"   />
          <line x1="-7.5" y1="-5"  x2="7.5"  y2="-5"  />
          <line x1="-8"   y1="5.5" x2="8"    y2="5.5" />
          <line x1="0"    y1="-9"  x2="-7.5" y2="-5"  />
          <line x1="0"    y1="-9"  x2="7.5"  y2="-5"  />
          <line x1="0"    y1="9.5" x2="-8"   y2="5.5" />
          <line x1="0"    y1="9.5" x2="8"    y2="5.5" />
        </g>

        {/* Neural nodes */}
        <g fill={`url(#${gid})`}>
          <circle cx="-7.5" cy="-5"  r="1.3" />
          <circle cx="7.5"  cy="-5"  r="1.3" />
          <circle cx="-8"   cy="5.5" r="1.3" />
          <circle cx="8"    cy="5.5" r="1.3" />
          <circle cx="0"    cy="-9"  r="1.15" />
          <circle cx="0"    cy="9.5" r="1.15" />
          <circle cx="-2.5" cy="0"   r="1.0" />
          <circle cx="2.5"  cy="0"   r="1.0" />
        </g>

        {/* Central luminous core (spark of intelligence) */}
        <circle cx="0" cy="0" r="2.6" fill={`url(#${cid})`} />
        <circle cx="0" cy="0" r="4.5" fill="none" stroke={`url(#${gid})`} strokeWidth="0.4" opacity="0.5" />
      </g>
    </svg>
  );
}
