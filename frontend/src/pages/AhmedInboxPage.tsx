import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Inbox, User, CreditCard, HelpCircle, Send, CheckCircle2,
  AlertCircle, Clock,
} from "lucide-react";
import clsx from "clsx";
import {
  getInbox, submitInboxAnswer, type InboxItem, type InboxPayload,
} from "@/api/inbox";

export function AhmedInboxPage() {
  const [inbox, setInbox] = useState<InboxPayload | null>(null);
  const [tab, setTab] = useState<"A" | "B" | "C">("A");

  async function refresh() {
    try {
      const data = await getInbox();
      setInbox(data);
    } catch (e) { console.error(e); }
  }
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10_000);
    return () => clearInterval(t);
  }, []);

  const counts = inbox?.counts || { A: 0, B: 0, C: 0, legacy: 0 };
  const items: InboxItem[] = inbox
    ? tab === "A" ? inbox.A_accounts
      : tab === "B" ? inbox.B_payments
      : inbox.C_clarifications
    : [];

  return (
    <div className="px-6 lg:px-10 py-10 max-w-5xl mx-auto">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.28em] text-gold-300/90 mb-1">
          <Inbox size={11}/> Ahmed Inbox
        </div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Votre boite de reception
        </h1>
        <p className="text-ink-300 text-sm mt-1">
          Le systeme ne vous demande QUE 3 choses : (A) ouvrir un compte,
          (B) payer un abonnement, ou (C) clarifier une decision. Tout le reste
          est fait en autonomie totale.
        </p>
      </motion.div>

      <div className="mt-8 flex items-center gap-3">
        <TabButton
          active={tab === "A"} onClick={() => setTab("A")}
          label="Comptes a ouvrir" count={counts.A}
          Icon={User} color="bg-blue-500/15 text-blue-300 border-blue-500/30"
        />
        <TabButton
          active={tab === "B"} onClick={() => setTab("B")}
          label="Paiements" count={counts.B}
          Icon={CreditCard} color="bg-orange-500/15 text-orange-300 border-orange-500/30"
        />
        <TabButton
          active={tab === "C"} onClick={() => setTab("C")}
          label="Clarifications" count={counts.C}
          Icon={HelpCircle} color="bg-yellow-500/15 text-yellow-200 border-yellow-500/30"
        />
      </div>

      <div className="mt-6 space-y-4">
        {items.length === 0 && (
          <div className="panel p-10 text-center text-ink-400">
            <CheckCircle2 size={36} className="mx-auto mb-3 text-success" />
            <div className="text-ink-200 text-sm">
              Aucune demande {tab} en attente. Le systeme travaille seul.
            </div>
          </div>
        )}
        {items.map((it) => (
          <InboxCard key={it.id} item={it} onResolved={refresh} />
        ))}
      </div>
    </div>
  );
}

function TabButton({
  active, onClick, label, count, Icon, color,
}: {
  active: boolean; onClick: () => void; label: string; count: number;
  Icon: typeof User; color: string;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "flex-1 panel p-4 text-left flex items-center gap-3 transition-all",
        active && "ring-1 ring-gold-500/30",
      )}
    >
      <span className={clsx("w-8 h-8 rounded-lg border flex items-center justify-center", color)}>
        <Icon size={14} />
      </span>
      <div className="flex-1">
        <div className="text-sm text-ink-50 font-medium">{label}</div>
        <div className="text-[11px] text-ink-400">
          {count} demande{count > 1 ? "s" : ""} en attente
        </div>
      </div>
      <div className="text-2xl font-semibold tabular-nums text-ink-50">{count}</div>
    </button>
  );
}

function InboxCard({ item, onResolved }: { item: InboxItem; onResolved: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await submitInboxAnswer(item.id, values);
      setDone(true);
      setTimeout(onResolved, 500);
    } finally { setBusy(false); }
  }

  if (done) {
    return (
      <div className="panel p-5 ring-1 ring-success/30 flex items-center gap-3">
        <CheckCircle2 size={16} className="text-success" />
        <div className="text-sm text-ink-100">
          Reponse envoyee. Le systeme continue en autonomie.
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      className={clsx(
        "panel p-5",
        item.form_type === "A" && "ring-1 ring-blue-500/20",
        item.form_type === "B" && "ring-1 ring-orange-500/20",
        item.form_type === "C" && "ring-1 ring-yellow-500/20",
      )}
    >
      <div className="flex items-start gap-3 mb-3">
        <TypeBadge type={item.form_type} />
        <div className="flex-1">
          <div className="text-sm text-ink-50 font-medium">
            {item.form_type === "A" && `Ouverture compte ${item.service_name}`}
            {item.form_type === "B" && `Paiement ${item.service_name} (${item.cost_amount} ${item.cost_currency})`}
            {item.form_type === "C" && `${item.question_id} - Clarification`}
          </div>
          <div className="text-[12px] text-ink-400 mt-1">{item.why}</div>
        </div>
        <Crit c={item.criticality} />
      </div>

      {item.form_type === "B" && item.payment_url && (
        <a
          href={item.payment_url} target="_blank" rel="noopener noreferrer"
          className="btn-primary text-xs mb-3"
        >
          <CreditCard size={12}/> Ouvrir page paiement
        </a>
      )}

      {item.form_type === "C" && item.suggested_answer && (
        <div className="panel-inner p-3 mb-3 text-[12.5px] text-ink-200">
          <span className="text-gold-300">Suggestion systeme :</span> {item.suggested_answer}
        </div>
      )}

      <div className="space-y-2">
        {item.fields.map((f) => (
          <div key={f.id}>
            <label className="text-[11px] uppercase tracking-[0.15em] text-ink-400">{f.label}</label>
            {f.type === "select" && f.options ? (
              <select
                value={values[f.id] || ""}
                onChange={(e) => setValues({ ...values, [f.id]: e.target.value })}
                className="input mt-1"
                required={f.required}
              >
                <option value="">Choisir...</option>
                {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : (
              <input
                type={f.type === "password" ? "password" : f.type === "email" ? "email" : "text"}
                value={values[f.id] || f.prefilled || ""}
                onChange={(e) => setValues({ ...values, [f.id]: e.target.value })}
                placeholder={f.placeholder || f.label}
                className="input mt-1 font-mono text-[12.5px]"
                required={f.required}
              />
            )}
          </div>
        ))}
      </div>

      <div className="mt-4 flex items-center justify-between">
        <div className="text-[10.5px] text-ink-500 flex items-center gap-1.5">
          <Clock size={10} /> expire {new Date(item.expires_at).toLocaleTimeString("fr-FR")}
        </div>
        <button onClick={submit} disabled={busy} className="btn-primary text-xs">
          <Send size={12}/> {busy ? "Envoi..." : "Valider"}
        </button>
      </div>
    </motion.div>
  );
}

function TypeBadge({ type }: { type: string | null }) {
  if (type === "A") return (
    <span className="chip-neutral bg-blue-500/15 text-blue-200 border-blue-500/30">
      <User size={11}/> A - Compte
    </span>
  );
  if (type === "B") return (
    <span className="chip-neutral bg-orange-500/15 text-orange-200 border-orange-500/30">
      <CreditCard size={11}/> B - Paiement
    </span>
  );
  if (type === "C") return (
    <span className="chip-neutral bg-yellow-500/15 text-yellow-200 border-yellow-500/30">
      <HelpCircle size={11}/> C - Question
    </span>
  );
  return <span className="chip-neutral">legacy</span>;
}

function Crit({ c }: { c: string }) {
  if (c === "critical") return <span className="chip-danger">critical</span>;
  if (c === "high") return <span className="chip-warn"><AlertCircle size={10}/> high</span>;
  return <span className="chip-neutral">{c}</span>;
}
