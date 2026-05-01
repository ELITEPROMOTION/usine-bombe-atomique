import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, AlertCircle, Info, X, AlertTriangle } from "lucide-react";
import clsx from "clsx";
import { slideInRight } from "./motion";

export type ToastTone = "success" | "warn" | "danger" | "info";

interface ToastEntry {
  id: string;
  tone: ToastTone;
  title: string;
  description?: string;
  duration_ms: number;
}

interface ToastApi {
  push: (
    t: Omit<ToastEntry, "id" | "duration_ms"> & { duration_ms?: number },
  ) => string;
  dismiss: (id: string) => void;
}

const ToastCtx = createContext<ToastApi | null>(null);

const TONE_META: Record<ToastTone, { icon: typeof Info; ring: string; bg: string; text: string }> = {
  success: { icon: CheckCircle2, ring: "border-success/40", bg: "bg-success/10", text: "text-success" },
  warn:    { icon: AlertTriangle, ring: "border-warn/40", bg: "bg-warn/10", text: "text-warn" },
  danger:  { icon: AlertCircle,  ring: "border-danger/40", bg: "bg-danger/10", text: "text-danger" },
  info:    { icon: Info,         ring: "border-info/40",  bg: "bg-info/10",  text: "text-info" },
};

let _seq = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastEntry[]>([]);

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback<ToastApi["push"]>((t) => {
    _seq += 1;
    const id = `t-${Date.now()}-${_seq}`;
    setItems((prev) => [...prev, { id, duration_ms: 4000, ...t }]);
    return id;
  }, []);

  // Auto-dismiss
  useEffect(() => {
    if (items.length === 0) return;
    const timers = items.map((t) =>
      setTimeout(() => dismiss(t.id), t.duration_ms),
    );
    return () => { timers.forEach(clearTimeout); };
  }, [items, dismiss]);

  const api = useMemo<ToastApi>(() => ({ push, dismiss }), [push, dismiss]);

  return (
    <ToastCtx.Provider value={api}>
      {children}
      <div className="fixed top-4 right-4 z-[1000] flex flex-col gap-2 w-80 pointer-events-none">
        <AnimatePresence>
          {items.map((t) => {
            const meta = TONE_META[t.tone];
            const Icon = meta.icon;
            return (
              <motion.div
                key={t.id}
                variants={slideInRight}
                initial="hidden" animate="show" exit="exit"
                className={clsx(
                  "panel pointer-events-auto px-4 py-3 flex items-start gap-3",
                  "border", meta.ring, meta.bg,
                )}
                role="status"
              >
                <Icon size={16} className={meta.text + " mt-0.5"} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-ink-50 tracking-tight">
                    {t.title}
                  </div>
                  {t.description && (
                    <div className="text-xs text-ink-300 mt-0.5">
                      {t.description}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => dismiss(t.id)}
                  className="text-ink-400 hover:text-ink-100 shrink-0"
                  aria-label="Fermer"
                >
                  <X size={14} />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastCtx);
  if (!ctx) {
    throw new Error("useToast must be used inside <ToastProvider>");
  }
  return ctx;
}
