import { motion } from "framer-motion";
import { Check, Clock, CircleDashed } from "lucide-react";
import clsx from "clsx";

export interface MilestoneItem {
  id: string;
  label: string;
  description: string;
  due_at: string;
  status: "pending" | "in_progress" | "done";
}

interface Props {
  items: MilestoneItem[];
}

const STATUS_LABEL: Record<MilestoneItem["status"], string> = {
  done: "Termine",
  in_progress: "En cours",
  pending: "A venir",
};

export function MilestoneTimeline({ items }: Props) {
  return (
    <ol className="relative pl-8">
      <div className="absolute left-3 top-2 bottom-2 w-px bg-gradient-to-b from-gold-500/40 via-ink-700 to-ink-800" />
      {items.map((m, i) => {
        const Icon =
          m.status === "done" ? Check
          : m.status === "in_progress" ? Clock
          : CircleDashed;
        return (
          <motion.li
            key={m.id}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            className="relative pb-7 last:pb-0"
          >
            <span className={clsx(
              "absolute -left-[26px] top-0 w-7 h-7 rounded-full flex items-center justify-center",
              "border",
              m.status === "done" && "bg-gold-500/20 border-gold-500/60 text-gold-200",
              m.status === "in_progress" && "bg-info/15 border-info/60 text-info",
              m.status === "pending" && "bg-ink-800 border-ink-700 text-ink-400",
            )}>
              <Icon size={14} />
            </span>
            <div className="flex flex-wrap items-baseline gap-x-3">
              <h4 className="font-medium text-ink-50 tracking-tight text-sm">
                {m.label}
              </h4>
              <span className={clsx(
                "text-[10px] uppercase tracking-[0.18em] font-medium",
                m.status === "done" && "text-gold-300",
                m.status === "in_progress" && "text-info",
                m.status === "pending" && "text-ink-400",
              )}>
                {STATUS_LABEL[m.status]}
              </span>
              <span className="text-[11px] text-ink-400 ml-auto tabular-nums">
                {new Date(m.due_at).toLocaleDateString("fr-FR", {
                  day: "2-digit", month: "short", year: "numeric",
                })}
              </span>
            </div>
            <p className="text-xs text-ink-300 mt-1 leading-relaxed">
              {m.description}
            </p>
          </motion.li>
        );
      })}
    </ol>
  );
}
