import { ReactNode } from "react";
import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import type { Status } from "./tokens";

export interface AlertBannerProps {
  status: Status;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  onClose?: () => void;
}

const ICON: Record<Status, ReactNode> = {
  success: <CheckCircle2 size={16} />,
  warning: <AlertTriangle size={16} />,
  error:   <XCircle size={16} />,
  info:    <Info size={16} />,
  neutral: <Info size={16} />,
};

const COLOR: Record<Status, string> = {
  success: "border-emerald-500/30 bg-emerald-500/5 text-emerald-100",
  warning: "border-yellow-500/30 bg-yellow-500/5 text-yellow-100",
  error:   "border-red-500/30 bg-red-500/5 text-red-100",
  info:    "border-blue-500/30 bg-blue-500/5 text-blue-100",
  neutral: "border-ink-700/50 bg-ink-800/30 text-ink-100",
};

export function AlertBanner({
  status, title, children, action, onClose,
}: AlertBannerProps) {
  return (
    <div
      className={clsx(
        "rounded-lg border px-4 py-3 flex items-start gap-3",
        COLOR[status],
      )}
    >
      <span className="shrink-0 mt-0.5">{ICON[status]}</span>
      <div className="flex-1 min-w-0">
        <div className="font-medium text-sm">{title}</div>
        {children && <div className="text-xs mt-1 opacity-90">{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
      {onClose && (
        <button
          onClick={onClose}
          className="shrink-0 text-ink-300 hover:text-ink-100 text-xs"
          aria-label="Fermer"
        >
          ×
        </button>
      )}
    </div>
  );
}
