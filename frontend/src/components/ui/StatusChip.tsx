import clsx from "clsx";
import { CheckCircle2, CircleSlash, Clock, AlertTriangle, Loader2 } from "lucide-react";

export type UiStatus =
  | "pending" | "running" | "executing" | "analyzing" | "planning" | "distributing" | "validating" | "reworking"
  | "success" | "completed"
  | "failed" | "timeout" | "cancelled"
  | "skipped";

const map: Record<UiStatus, { cls: string; label: string; Icon: typeof Clock }> = {
  pending:      { cls: "chip-neutral", label: "En attente",    Icon: Clock },
  running:      { cls: "chip-gold",    label: "En cours",      Icon: Loader2 },
  executing:    { cls: "chip-gold",    label: "Execution",     Icon: Loader2 },
  analyzing:    { cls: "chip-gold",    label: "Analyse",       Icon: Loader2 },
  planning:     { cls: "chip-gold",    label: "Planification", Icon: Loader2 },
  distributing: { cls: "chip-gold",    label: "Distribution",  Icon: Loader2 },
  validating:   { cls: "chip-gold",    label: "Validation",    Icon: Loader2 },
  reworking:    { cls: "chip-warn",    label: "Reprise",       Icon: Loader2 },
  success:      { cls: "chip-success", label: "Succes",        Icon: CheckCircle2 },
  completed:    { cls: "chip-success", label: "Complete",      Icon: CheckCircle2 },
  failed:       { cls: "chip-danger",  label: "Echec",         Icon: AlertTriangle },
  timeout:      { cls: "chip-danger",  label: "Timeout",       Icon: AlertTriangle },
  cancelled:    { cls: "chip-neutral", label: "Annule",        Icon: CircleSlash },
  skipped:      { cls: "chip-neutral", label: "Ignore",        Icon: CircleSlash },
};

export function StatusChip({ status, compact }: { status: string; compact?: boolean }) {
  const info = map[status as UiStatus] ?? { cls: "chip-neutral", label: status, Icon: Clock };
  const spinning = ["running", "executing", "analyzing", "planning", "distributing", "validating", "reworking"].includes(status);
  return (
    <span className={clsx(info.cls, compact && "px-2 py-0")}>
      <info.Icon size={compact ? 10 : 12} className={clsx(spinning && "animate-spin")} />
      {info.label}
    </span>
  );
}
