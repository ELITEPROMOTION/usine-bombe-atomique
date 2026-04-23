import { ReactNode, useEffect } from "react";
import clsx from "clsx";
import { X } from "lucide-react";
import { ActionButton } from "./Button";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
}

export function Modal({
  open, onClose, title, children, footer, size = "md",
}: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal
        className={clsx(
          "relative w-full rounded-xl border border-ink-700/60 bg-ink-900 shadow-panel",
          "max-h-[90vh] flex flex-col",
          size === "sm" && "max-w-md",
          size === "md" && "max-w-xl",
          size === "lg" && "max-w-3xl",
        )}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-800">
          <h2 className="font-display text-lg font-semibold text-ink-50">{title}</h2>
          <button
            onClick={onClose}
            className="text-ink-300 hover:text-ink-100 transition"
            aria-label="Fermer"
          >
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4 text-sm text-ink-200">
          {children}
        </div>
        {footer && (
          <div className="px-5 py-3 border-t border-ink-800 flex justify-end gap-2">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

export function ConfirmModal({
  open, onClose, onConfirm, title, message, confirmLabel = "Confirmer",
  variant = "primary",
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  title: ReactNode;
  message: ReactNode;
  confirmLabel?: string;
  variant?: "primary" | "danger";
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      footer={
        <>
          <ActionButton variant="ghost" onClick={onClose}>Annuler</ActionButton>
          <ActionButton variant={variant} onClick={() => { onConfirm(); onClose(); }}>
            {confirmLabel}
          </ActionButton>
        </>
      }
    >
      {message}
    </Modal>
  );
}
