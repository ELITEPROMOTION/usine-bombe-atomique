import { motion } from "framer-motion";
import { Download, FileText, Image, Package, Sparkles, FileCode } from "lucide-react";
import clsx from "clsx";

export interface DeliverableLike {
  id: string;
  name: string;
  category: "code" | "design" | "doc" | "media" | "package";
  size_bytes: number;
  released_at: string;
  download_token: string;
  preview_url: string | null;
}

interface Props {
  deliverable: DeliverableLike;
  downloadUrl: string;
}

const ICONS = {
  code: FileCode,
  design: Sparkles,
  doc: FileText,
  media: Image,
  package: Package,
} as const;

const CATEGORY_LABEL: Record<DeliverableLike["category"], string> = {
  code: "Code",
  design: "Design",
  doc: "Document",
  media: "Media",
  package: "Package",
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(1)} GB`;
}

export function DeliverableCard({ deliverable, downloadUrl }: Props) {
  const Icon = ICONS[deliverable.category];
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -2 }}
      className={clsx(
        "panel p-5 flex items-start gap-4",
        "transition-all hover:border-gold-500/50",
      )}
    >
      <div className="w-11 h-11 rounded-lg bg-gradient-to-br from-ink-800 to-ink-900 border border-ink-700/70 flex items-center justify-center text-gold-300">
        <Icon size={18} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <h3 className="font-medium text-ink-50 tracking-tight truncate">
            {deliverable.name}
          </h3>
          <span className="text-[10px] uppercase tracking-[0.18em] text-ink-400">
            {CATEGORY_LABEL[deliverable.category]}
          </span>
        </div>
        <div className="text-[11px] text-ink-400 mt-1 tabular-nums">
          {formatBytes(deliverable.size_bytes)} ·{" "}
          {new Date(deliverable.released_at).toLocaleDateString("fr-FR", {
            day: "2-digit", month: "short", year: "numeric",
          })}
        </div>
      </div>
      <a
        href={downloadUrl}
        target="_blank"
        rel="noreferrer"
        className="btn-outline shrink-0"
        aria-label={`Telecharger ${deliverable.name}`}
      >
        <Download size={14} /> Telecharger
      </a>
    </motion.div>
  );
}
