import { useEffect, useMemo, useState } from "react";
import { Shield, ScrollText, Eye, AlertTriangle, FileSignature, RefreshCw, Download } from "lucide-react";
import clsx from "clsx";
import {
  AuditEvent,
  ConsentSummary,
  DashboardSummary,
  OsintModule,
  checkAuditIntegrity,
  exportAudit,
  getDashboardSummary,
  listConsents,
  listModules,
} from "@/api/osint";

type Tab = "security" | "monitoring" | "threat" | "consent" | "audit";

const TABS: { key: Tab; label: string; Icon: typeof Shield }[] = [
  { key: "security",   label: "Securite Dendani",    Icon: Shield },
  { key: "monitoring", label: "Brand Monitoring",    Icon: Eye },
  { key: "threat",     label: "Threat Intelligence", Icon: AlertTriangle },
  { key: "consent",    label: "Pentest Consenti",    Icon: FileSignature },
  { key: "audit",      label: "Audit Trail",         Icon: ScrollText },
];

export function OSINTDashboardPage() {
  const [tab, setTab] = useState<Tab>("security");
  const [modules, setModules] = useState<OsintModule[]>([]);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [consents, setConsents] = useState<ConsentSummary[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [integrity, setIntegrity] = useState<{ ok: boolean; checked: number; broken: number } | null>(null);
  const [loading, setLoading] = useState(false);

  async function refreshAll() {
    setLoading(true);
    try {
      const [m, s, c] = await Promise.all([
        listModules().catch(() => [] as OsintModule[]),
        getDashboardSummary().catch(() => null),
        listConsents().then((d) => d.consents).catch(() => [] as ConsentSummary[]),
      ]);
      setModules(m);
      setSummary(s);
      setConsents(c);
    } finally {
      setLoading(false);
    }
  }

  async function refreshAudit() {
    const [a, i] = await Promise.all([
      exportAudit({ limit: 100 }).then((d) => d.events).catch(() => [] as AuditEvent[]),
      checkAuditIntegrity().catch(() => null),
    ]);
    setAudit(a);
    if (i) setIntegrity({ ok: i.integrity_ok, checked: i.events_checked, broken: i.broken.length });
  }

  useEffect(() => {
    void refreshAll();
    void refreshAudit();
  }, []);

  return (
    <div className="px-6 lg:px-10 py-10 max-w-6xl mx-auto">
      <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300/90 mb-1">Defensive</div>
      <h1 className="font-display text-3xl font-semibold tracking-tight">OSINT — usage legal</h1>
      <p className="text-ink-300 text-sm mt-2">
        12 modules defensifs. Garde-fous techniques non-contournables. Audit trail
        immuable RGPD-DZ. Aucun module ne peut viser une cible hors-scope.
      </p>

      <div className="mt-6 flex flex-wrap gap-2 border-b border-ink-800">
        {TABS.map(({ key, label, Icon }) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={clsx(
              "inline-flex items-center gap-2 px-4 py-2.5 -mb-px text-sm border-b-2 transition",
              tab === key
                ? "border-gold-400 text-ink-50"
                : "border-transparent text-ink-300 hover:text-ink-100",
            )}
          >
            <Icon size={14} />
            {label}
          </button>
        ))}
        <div className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={refreshAll}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded text-xs bg-ink-800 text-ink-100 hover:bg-ink-700"
          >
            <RefreshCw size={14} className={clsx(loading && "animate-spin")} />
            Refresh
          </button>
        </div>
      </div>

      <div className="mt-6">
        {tab === "security" && <SecurityTab modules={modules} summary={summary} />}
        {tab === "monitoring" && <MonitoringTab modules={modules} />}
        {tab === "threat" && <ThreatTab modules={modules} />}
        {tab === "consent" && <ConsentTab consents={consents} onChange={refreshAll} />}
        {tab === "audit" && <AuditTab audit={audit} integrity={integrity} onRefresh={refreshAudit} />}
      </div>
    </div>
  );
}

function ModuleCard({ mod }: { mod: OsintModule }) {
  const riskColor = {
    low:      "text-emerald-300",
    medium:   "text-amber-300",
    high:     "text-orange-300",
    critical: "text-red-300",
  }[mod.risk];
  const scopeBadge = {
    dendani_only:      "Dendani only",
    public_sources:    "Sources publiques",
    requires_consent:  "Consent requis",
  }[mod.scope];
  return (
    <div className="panel p-4">
      <div className="flex items-start justify-between">
        <h3 className="font-display text-ink-50 text-sm">{mod.name}</h3>
        <span className={clsx("text-[10px] uppercase font-bold", riskColor)}>{mod.risk}</span>
      </div>
      <div className="mt-1 text-[11px] text-ink-300">{mod.category}</div>
      <div className="mt-2 inline-block px-2 py-0.5 rounded bg-ink-800 text-[10px] text-ink-200">
        {scopeBadge}
      </div>
    </div>
  );
}

function SecurityTab({ modules, summary }: { modules: OsintModule[]; summary: DashboardSummary | null }) {
  const security = modules.filter((m) => m.category === "security_defensive");
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Modules defensifs" value={String(security.length)} />
        <Stat label="Decisions 7j" value={String(summary?.decisions_7d.reduce((a, d) => a + d.count, 0) || 0)} />
        <Stat label="Refus auto 7j"
              value={String(summary?.decisions_7d.find((d) => d.decision === "denied")?.count || 0)} />
        <Stat label="Consents actifs" value={String(summary?.active_consents || 0)} />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {security.map((m) => <ModuleCard key={m.name} mod={m} />)}
      </div>
    </div>
  );
}

function MonitoringTab({ modules }: { modules: OsintModule[] }) {
  const watch = modules.filter((m) => m.category === "public_watch");
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {watch.map((m) => <ModuleCard key={m.name} mod={m} />)}
    </div>
  );
}

function ThreatTab({ modules }: { modules: OsintModule[] }) {
  const ti = modules.filter((m) => m.category === "threat_intel");
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {ti.map((m) => <ModuleCard key={m.name} mod={m} />)}
    </div>
  );
}

function ConsentTab({ consents, onChange }: { consents: ConsentSummary[]; onChange: () => void }) {
  return (
    <div className="space-y-6">
      <div className="text-sm text-ink-200">
        Liste des contrats consentement actifs. Tout pentest externe necessite un
        consent valide signe avant declenchement.
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wider text-ink-400">
              <th className="py-2 pr-3">Target</th>
              <th className="py-2 pr-3">Contractor</th>
              <th className="py-2 pr-3">Actions</th>
              <th className="py-2 pr-3">Expire le</th>
            </tr>
          </thead>
          <tbody className="text-ink-100">
            {consents.length === 0 && (
              <tr><td colSpan={4} className="py-6 text-center text-ink-400">Aucun consent actif.</td></tr>
            )}
            {consents.map((c) => (
              <tr key={c.consent_id} className="border-t border-ink-800">
                <td className="py-2 pr-3 font-mono text-xs">{c.target}</td>
                <td className="py-2 pr-3">{c.contractor}</td>
                <td className="py-2 pr-3 text-xs">{c.actions.join(", ")}</td>
                <td className="py-2 pr-3 text-xs">{c.expires_at?.slice(0, 10) ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AuditTab({
  audit,
  integrity,
  onRefresh,
}: {
  audit: AuditEvent[];
  integrity: { ok: boolean; checked: number; broken: number } | null;
  onRefresh: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-ink-400">Integrite chaine hash</div>
          {integrity ? (
            <div className={clsx("text-xl font-display mt-1",
                                  integrity.ok ? "text-emerald-300" : "text-red-300")}>
              {integrity.ok
                ? `OK — ${integrity.checked} events`
                : `CORRUPTION — ${integrity.broken} broken / ${integrity.checked} checked`}
            </div>
          ) : (
            <div className="text-ink-400">verification...</div>
          )}
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded text-xs bg-ink-800 text-ink-100 hover:bg-ink-700"
        >
          <Download size={14} /> Recharger
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wider text-ink-400">
              <th className="py-2 pr-2">Date</th>
              <th className="py-2 pr-2">Module</th>
              <th className="py-2 pr-2">Action</th>
              <th className="py-2 pr-2">Target</th>
              <th className="py-2 pr-2">Decision</th>
              <th className="py-2 pr-2">Risk</th>
            </tr>
          </thead>
          <tbody>
            {audit.length === 0 && (
              <tr><td colSpan={6} className="py-6 text-center text-ink-400">Audit trail vide.</td></tr>
            )}
            {audit.map((e) => (
              <tr key={e.event_id} className="border-t border-ink-800 text-ink-100">
                <td className="py-1 pr-2 text-[11px] text-ink-400">{e.created_at.slice(11, 19)}</td>
                <td className="py-1 pr-2 text-xs">{e.module}</td>
                <td className="py-1 pr-2 text-xs">{e.action}</td>
                <td className="py-1 pr-2 font-mono text-[11px] truncate max-w-[200px]">{e.target}</td>
                <td className="py-1 pr-2 text-xs">
                  <span className={clsx(
                    "px-1.5 py-0.5 rounded",
                    e.decision === "allowed" && "bg-emerald-950/40 text-emerald-300",
                    e.decision === "denied" && "bg-red-950/40 text-red-300",
                    e.decision === "error" && "bg-amber-950/40 text-amber-300",
                  )}>{e.decision}</span>
                </td>
                <td className="py-1 pr-2 text-[10px] uppercase">{e.risk_level}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel p-4">
      <div className="text-[11px] uppercase tracking-wider text-ink-400">{label}</div>
      <div className="mt-1 text-2xl font-display text-ink-50">{value}</div>
    </div>
  );
}
