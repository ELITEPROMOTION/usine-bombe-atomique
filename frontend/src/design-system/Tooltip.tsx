import { useState, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import clsx from "clsx";

interface Props {
  content: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  delay_ms?: number;
  children: React.ReactElement;
}

const SIDE_CLASS = {
  top:    "bottom-[calc(100%+6px)] left-1/2 -translate-x-1/2",
  bottom: "top-[calc(100%+6px)]    left-1/2 -translate-x-1/2",
  left:   "right-[calc(100%+6px)]  top-1/2 -translate-y-1/2",
  right:  "left-[calc(100%+6px)]   top-1/2 -translate-y-1/2",
} as const;

export function Tooltip({ content, side = "top", delay_ms = 200, children }: Props) {
  const [open, setOpen] = useState(false);
  const timer = useRef<number | null>(null);

  const onEnter = () => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(true), delay_ms);
  };
  const onLeave = () => {
    if (timer.current) window.clearTimeout(timer.current);
    setOpen(false);
  };

  return (
    <span
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      onFocus={onEnter}
      onBlur={onLeave}
      className="relative inline-flex"
    >
      {children}
      <AnimatePresence>
        {open && (
          <motion.span
            role="tooltip"
            initial={{ opacity: 0, y: 2 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 2 }}
            transition={{ duration: 0.12 }}
            className={clsx(
              "absolute z-50 whitespace-nowrap pointer-events-none",
              "px-2 py-1 rounded-md text-[11px]",
              "bg-ink-950/95 border border-ink-700 text-ink-100 shadow-lg",
              SIDE_CLASS[side],
            )}
          >
            {content}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}
