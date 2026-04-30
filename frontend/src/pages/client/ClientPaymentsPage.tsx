import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Receipt, AlertCircle, ExternalLink } from "lucide-react";
import {
  invoicePdfUrl,
  listClientHandoffs,
  listClientInvoices,
  type ClientHandoff,
  type ClientInvoice,
} from "@/api/client_payments";
import { InvoicePreview } from "@/design-system";

export function ClientPaymentsPage() {
  const [invoices, setInvoices] = useState<ClientInvoice[]>([]);
  const [handoffs, setHandoffs] = useState<ClientHandoff[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([listClientInvoices(), listClientHandoffs()]).then(
      ([i, h]) => {
        setInvoices(i);
        setHandoffs(h);
        setLoading(false);
      },
    );
  }, []);

  const totalPaid = invoices
    .filter((i) => i.status === "paid")
    .reduce((s, i) => s + i.amount_cents, 0);
  const totalPending = invoices
    .filter((i) => i.status === "issued")
    .reduce((s, i) => s + i.amount_cents, 0);
  const currency = invoices[0]?.currency ?? "EUR";

  const paymentHandoffs = handoffs.filter(
    (h) => h.action_type === "payment_confirm",
  );

  return (
    <div className="px-6 lg:px-10 py-10 max-w-5xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300/90 mb-1">
          Facturation
        </div>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-ink-50">
          Paiements
        </h1>
        <p className="text-ink-300 text-sm mt-1">
          Toutes vos factures et paiements en un seul endroit.
        </p>
      </motion.div>

      <div className="grid sm:grid-cols-2 gap-4 mb-8">
        <SummaryCard
          label="Deja regle"
          amount={totalPaid}
          currency={currency}
          tone="success"
        />
        <SummaryCard
          label="A regler"
          amount={totalPending}
          currency={currency}
          tone={totalPending > 0 ? "warn" : "neutral"}
        />
      </div>

      {paymentHandoffs.length > 0 && (
        <div className="panel p-5 mb-8 border-warn/40 bg-warn/5">
          <div className="flex items-start gap-3">
            <AlertCircle size={18} className="text-warn shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-medium text-ink-50 tracking-tight">
                Action de paiement requise
              </h3>
              {paymentHandoffs.map((h) => (
                <div key={h.id} className="mt-2 flex items-center gap-3">
                  <div className="text-sm text-ink-200">{h.title}</div>
                  <a
                    href={h.cta_url}
                    className="ml-auto btn-primary"
                  >
                    {h.cta_label} <ExternalLink size={13} />
                  </a>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="mb-3 flex items-baseline gap-2">
        <Receipt size={14} className="text-gold-300" />
        <h2 className="font-medium text-ink-50 tracking-tight">
          Historique des factures
        </h2>
      </div>
      {loading && <div className="text-ink-400 text-sm">Chargement...</div>}
      <div className="space-y-3">
        {invoices.map((i) => (
          <InvoicePreview
            key={i.invoice_id}
            invoice={i}
            pdfUrl={invoicePdfUrl(i.pdf_token)}
          />
        ))}
      </div>
    </div>
  );
}

interface SummaryProps {
  label: string;
  amount: number;
  currency: string;
  tone: "success" | "warn" | "neutral";
}

function SummaryCard({ label, amount, currency, tone }: SummaryProps) {
  const formatted = new Intl.NumberFormat("fr-FR", {
    style: "currency", currency, maximumFractionDigits: 2,
  }).format(amount / 100);
  const toneClass =
    tone === "success" ? "text-success"
    : tone === "warn" ? "text-warn"
    : "text-ink-100";

  return (
    <div className="panel p-5">
      <div className="text-xs uppercase tracking-[0.2em] text-ink-400">
        {label}
      </div>
      <div className={`mt-2 font-display text-3xl font-semibold tracking-tight tabular-nums ${toneClass}`}>
        {formatted}
      </div>
    </div>
  );
}
