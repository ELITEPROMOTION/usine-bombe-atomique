/**
 * Design tokens UBA - couleurs, typographie, espacement.
 * Consommes par les composants design-system + tailwind.config.js.
 */

export const colors = {
  // Ink neutrals (dark luxe)
  ink: {
    950: "#060607",
    900: "#0a0a0c",
    850: "#0e0e11",
    800: "#141418",
    700: "#1c1c22",
    600: "#26262e",
    500: "#33333d",
    400: "#4a4a57",
    300: "#6a6a79",
    200: "#9a9aa8",
    100: "#c7c7cf",
    50:  "#eaeaee",
  },
  // Accent gold
  gold: {
    300: "#e7c05b",
    400: "#d9a63c",
    500: "#c49129",
  },
  // Status
  success: "#3ecf8e",
  warn:    "#f7c948",
  danger:  "#ef5b5b",
  info:    "#4a90e2",
  neutral: "#6a6a79",
} as const;

export const typography = {
  fontFamily: {
    sans: "Inter, ui-sans-serif, system-ui, sans-serif",
    mono: "'JetBrains Mono', ui-monospace, monospace",
  },
  sizes: {
    h1: { size: "1.875rem", weight: 600, tracking: "-0.02em" },
    h2: { size: "1.5rem",   weight: 600, tracking: "-0.015em" },
    h3: { size: "1.125rem", weight: 500, tracking: "-0.01em" },
    body: { size: "0.875rem", weight: 400 },
    small: { size: "0.75rem", weight: 400 },
    micro: { size: "0.6875rem", weight: 500, tracking: "0.12em", uppercase: true },
  },
} as const;

export const spacing = {
  xs: "0.25rem",
  sm: "0.5rem",
  md: "1rem",
  lg: "1.5rem",
  xl: "2rem",
  xxl: "3rem",
} as const;

export const radii = {
  sm: "0.375rem",
  md: "0.5rem",
  lg: "0.75rem",
  xl: "1rem",
  pill: "9999px",
} as const;

export const shadows = {
  panel: "0 1px 0 rgba(255,255,255,0.04) inset, 0 24px 64px -24px rgba(0,0,0,0.8)",
  glow:  "0 0 32px -8px rgba(231, 192, 91, 0.35)",
  lift:  "0 8px 24px -8px rgba(0,0,0,0.6)",
} as const;

export type Status = "success" | "warning" | "error" | "info" | "neutral";

export const STATUS_COLOR: Record<Status, string> = {
  success: colors.success,
  warning: colors.warn,
  error:   colors.danger,
  info:    colors.info,
  neutral: colors.neutral,
};
