import { motion } from "framer-motion";
import { FileText, ExternalLink } from "lucide-react";
import clsx from "clsx";

export interface InvoiceLike {
  invoice_id: string;
  number: string;
  amount_cents: number;
  currency: string;
  status: "draft" | "issued" | "paid" | "refunded";
  issued_at: string;
  paid_at: string | null;
  pdf_token: string;
}

interface Props {
  invoice: InvoiceLike;
  pdfUrl: string;
}

const STATUS_META: Record<InvoiceLike["status"], { label: string; chip: string }> = {
  draft:    { label: "Brouillon",  chip: "chip-neutral" },
  issued:   { label: "A regler",   chip: "chip-warn" },
  paid:     { label: "Reglee",     chip: "chip-success" },
  refunded: { label: "Remboursee", chip: "chip-danger" },
};

function formatAmount(cents: number, currency: string): string {
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

export function InvoicePreview({ invoice, pdfUrl }: Props) {
  const meta = STATUS_META[invoice.status];
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="panel p-5 flex items-center gap-4"
    >
      <div className="w-11 h-11 rounded-lg bg-ink-800/80 border border-ink-700/70 flex items-center justify-center text-gold-300">
        <FileText size={17} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="font-mono text-sm text-ink-100 tracking-tight">
            {invoice.number}
          </span>
          <span className={clsx("font-medium", meta.chip)}>
            {meta.label}
          </span>
        </div>
        <div className="text-[11px] text-ink-400 mt-1 tabular-nums">
          Emise le{" "}
          {new Date(invoice.issued_at).toLocaleDateString("fr-FR", {
            day: "2-digit", month: "short", year: "numeric",
          })}
          {invoice.paid_at && (
            <>
              {" · Reglee le "}
              {new Date(invoice.paid_at).toLocaleDateString("fr-FR", {
                day: "2-digit", month: "short", year: "numeric",
              })}
            </>
          )}
        </div>
      </div>
      <div className="text-right">
        <div className="font-display text-lg font-semibold text-ink-50 tabular-nums">
          {formatAmount(invoice.amount_cents, invoice.currency)}
        </div>
        <a
          href={pdfUrl}
          target="_blank"
          rel="noreferrer"
          className="text-[11px] text-gold-300 hover:text-gold-200 inline-flex items-center gap-1 mt-0.5"
        >
          PDF <ExternalLink size={11} />
        </a>
      </div>
    </motion.div>
  );
}
