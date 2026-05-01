import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import clsx from "clsx";

interface Props {
  open: boolean;
  onClose: () => void;
  side?: "right" | "left";
  title?: string;
  description?: string;
  children: React.ReactNode;
  width?: string;
}

export function Sheet({
  open, onClose, side = "right", title, description, children,
  width = "440px",
}: Props) {
  // ESC to close
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="fixed inset-0 z-[900] bg-black/65 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden
          />
          <motion.aside
            key="sheet"
            role="dialog"
            aria-modal="true"
            aria-label={title}
            initial={{ x: side === "right" ? "100%" : "-100%" }}
            animate={{ x: 0 }}
            exit={{ x: side === "right" ? "100%" : "-100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 32 }}
            style={{ width }}
            className={clsx(
              "fixed top-0 bottom-0 z-[901] flex flex-col",
              "bg-ink-900/95 backdrop-blur border-ink-700/60 shadow-panel",
              side === "right"
                ? "right-0 border-l"
                : "left-0 border-r",
            )}
          >
            <header className="px-5 py-4 hairline flex items-start justify-between">
              <div className="min-w-0">
                {title && (
                  <h2 className="font-display text-lg font-semibold tracking-tight text-ink-50">
                    {title}
                  </h2>
                )}
                {description && (
                  <p className="text-xs text-ink-400 mt-0.5">
                    {description}
                  </p>
                )}
              </div>
              <button
                onClick={onClose}
                className="text-ink-400 hover:text-ink-100 p-1.5 rounded-md hover:bg-ink-800"
                aria-label="Fermer"
              >
                <X size={16} />
              </button>
            </header>
            <div className="flex-1 overflow-y-auto p-5">
              {children}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
