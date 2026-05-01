import type { LucideIcon } from "lucide-react";
import { motion } from "framer-motion";
import clsx from "clsx";

interface Props {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({ icon: Icon, title, description, action, className }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className={clsx(
        "panel p-10 flex flex-col items-center text-center",
        className,
      )}
    >
      <div className="w-14 h-14 rounded-2xl bg-ink-800/60 border border-ink-700/60 flex items-center justify-center mb-4 text-gold-300">
        <Icon size={22} />
      </div>
      <h3 className="font-display text-lg font-semibold tracking-tight text-ink-50">
        {title}
      </h3>
      {description && (
        <p className="text-sm text-ink-300 mt-2 max-w-md">
          {description}
        </p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </motion.div>
  );
}
