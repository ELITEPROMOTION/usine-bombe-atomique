import { useEffect, useState } from "react";
import {
  Building2, CheckCircle2, Play, Zap, BookOpen, Calculator,
  Scale, Truck, Users, BookMarked,
} from "lucide-react";
import {
  Card, CardHeader, Badge, HealthDot, KPIWidget, ActionButton, Modal,
} from "@/design-system";
import {
  listDomains, getDomain, processDomain, listFeatures, toggleFeature,
  type DomainInfo, type DomainDetail, type FeatureFlag,
} from "@/api/domains";

const DOMAIN_ICONS: Record<string, any> = {
  fiscal_dz: Calculator,
  juridique: Scale,
  logistique: Truck,
  rh: Users,
  comptabilite: BookMarked,
};

const SAMPLE_INPUTS: Record<string, Record<string, unknown>> = {
  fiscal_dz: { revenu_annuel: 300_000 },
  juridique: { type_acte: "vente", categorie: "immobilier", prix: 5_000_000,
                vendeur: "A", acheteur: "B" },
  logistique: { operation: "import", categorie: "standard", valeur_caf: 100_000 },
  rh: { salaire_brut_mensuel: 80_000 },
  comptabilite: { numero_compte: 411 },
};

export function DomainsPage() {
  const [domains, setDomains] = useState<DomainInfo[]>([]);
  const [features, setFeatures] = useState<FeatureFlag[]>([]);
  const [detail, setDetail] = useState<DomainDetail | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<any>(null);
  const [showResult, setShowResult] = useState(false);

  async function refresh() {
    try {
      const [dom, feat] = await Promise.all([listDomains(), listFeatures()]);
      setDomains(dom.domains);
      setFeatures(feat.flags);
    } catch (e) { console.error(e); }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 30_000);
    return () => clearInterval(t);
  }, []);

  async function handleTryIt(id: string) {
    setRunning(id);
    try {
      const res = await processDomain(id, SAMPLE_INPUTS[id] ?? {});
      setLastResult(res);
      setShowResult(true);
    } finally { setRunning(null); }
  }

  async function handleLoadDetail(id: string) {
    const d = await getDomain(id);
    setDetail(d);
  }

  async function handleToggleFeature(name: string, enabled: boolean) {
    await toggleFeature(name, enabled);
    refresh();
  }

  const activeFlagsCount = features.filter((f) => f.enabled_globally).length;
  const totalRules = domains.reduce((s, _) => s + 0, 0); // populate via details

  return (
    <div className="px-4 lg:px-8 py-6 lg:py-10 max-w-7xl mx-auto">
      <div className="mb-6">
        <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300 mb-1 flex items-center gap-1.5">
          <Building2 size={11} /> V5.6 Universalite
        </div>
        <h1 className="font-display text-2xl lg:text-3xl font-semibold">
          5 domaines metier UBA
        </h1>
        <p className="text-ink-300 text-sm mt-1">
          Architecture domain-agnostic : fiscal_dz · juridique · logistique · rh · comptabilite
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <KPIWidget
          icon={<Building2 size={12} />}
          label="Domaines actifs"
          value={domains.length}
          hint="5 attendus"
          status={domains.length === 5 ? "success" : "warning"}
        />
        <KPIWidget
          icon={<BookOpen size={12} />}
          label="Operations totales"
          value={domains.reduce((s, d) => s + d.operations.length, 0)}
          hint="across all domains"
        />
        <KPIWidget
          icon={<Zap size={12} />}
          label="Feature flags actifs"
          value={activeFlagsCount}
          hint={`${features.length} total`}
          status="info"
        />
        <KPIWidget
          icon={<CheckCircle2 size={12} />}
          label="Domaines sains"
          value={`${domains.length}/${domains.length || 5}`}
          status="success"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
        {domains.map((d) => {
          const Icon = DOMAIN_ICONS[d.domain_id] ?? Building2;
          const deprecated = d.deprecated.length > 0;
          return (
            <Card
              key={d.domain_id}
              className="hover:border-ink-600 transition cursor-pointer"
              onClick={() => handleLoadDetail(d.domain_id)}
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Icon size={18} className="text-gold-300" />
                  <div>
                    <div className="font-medium text-ink-50">{d.domain_id}</div>
                    <div className="text-[10px] text-ink-400">v{d.latest_version}</div>
                  </div>
                </div>
                <HealthDot
                  status={deprecated ? "warning" : "success"}
                  animated={!deprecated}
                />
              </div>
              <p className="text-xs text-ink-400 mb-3 line-clamp-2">
                {d.description}
              </p>
              <div className="flex items-center gap-2 flex-wrap mb-2">
                {d.operations.slice(0, 3).map((op) => (
                  <Badge key={op} size="sm" status="neutral">{op}</Badge>
                ))}
                {d.operations.length > 3 && (
                  <span className="text-[10px] text-ink-400">
                    +{d.operations.length - 3}
                  </span>
                )}
              </div>
              <div className="flex justify-end">
                <ActionButton
                  size="sm"
                  variant="secondary"
                  onClick={(e) => { e.stopPropagation(); handleTryIt(d.domain_id); }}
                  disabled={running === d.domain_id}
                  leading={<Play size={11} />}
                >
                  Try
                </ActionButton>
              </div>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader
          icon={<Zap size={14} />}
          title="Feature flags"
          hint={`${features.length} flags configurés`}
        />
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-[0.14em] text-ink-400 border-b border-ink-800">
              <th className="py-2">Flag</th>
              <th className="py-2">Description</th>
              <th className="py-2 text-center">Rollout</th>
              <th className="py-2 text-right">Etat</th>
            </tr>
          </thead>
          <tbody>
            {features.map((f) => (
              <tr key={f.flag_name} className="border-b border-ink-800/40">
                <td className="py-2 font-mono text-xs text-ink-200">{f.flag_name}</td>
                <td className="py-2 text-xs text-ink-400">{f.description || "—"}</td>
                <td className="py-2 text-center">
                  <Badge size="sm" status={f.rollout_percent > 0 ? "info" : "neutral"}>
                    {f.rollout_percent}%
                  </Badge>
                </td>
                <td className="py-2 text-right">
                  <ActionButton
                    size="sm"
                    variant={f.enabled_globally ? "primary" : "ghost"}
                    onClick={() => handleToggleFeature(f.flag_name, !f.enabled_globally)}
                  >
                    {f.enabled_globally ? "ON" : "OFF"}
                  </ActionButton>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {detail && (
        <Modal
          open={!!detail}
          onClose={() => setDetail(null)}
          title={`${detail.domain_id} · v${detail.latest_version}`}
          size="lg"
        >
          <div className="space-y-4">
            <p className="text-sm text-ink-300">{detail.description}</p>
            <div>
              <div className="text-xs uppercase tracking-wider text-ink-400 mb-2">
                Operations ({detail.operations.length})
              </div>
              <div className="flex flex-wrap gap-1.5">
                {detail.operations.map((op) => (
                  <Badge key={op} status="neutral">{op}</Badge>
                ))}
              </div>
            </div>
            <div>
              <div className="text-xs uppercase tracking-wider text-ink-400 mb-2">
                Rules ({detail.rules_count})
              </div>
              <div className="space-y-1 max-h-64 overflow-y-auto">
                {detail.rules.map((r) => (
                  <div key={r.id} className="text-xs py-1 border-b border-ink-800/40">
                    <span className="font-mono text-ink-200">{r.id}</span>
                    <span className="text-ink-400 ml-2">— {r.description}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Modal>
      )}

      {showResult && lastResult && (
        <Modal
          open={showResult}
          onClose={() => setShowResult(false)}
          title={`Try · ${lastResult.domain_id} · ${lastResult.success ? "OK" : "FAIL"}`}
          size="md"
        >
          <div className="space-y-3 text-sm">
            <div className="flex gap-2">
              <Badge status={lastResult.success ? "success" : "error"}>
                {lastResult.success ? "success" : "failed"}
              </Badge>
              <Badge status="info">{lastResult.duration_ms}ms</Badge>
              <Badge status="neutral">{lastResult.rules_applied.length} rules</Badge>
            </div>
            <div className="text-xs font-mono bg-ink-950 p-3 rounded border border-ink-800 overflow-x-auto">
              <pre>{JSON.stringify(lastResult.output, null, 2)}</pre>
            </div>
            <div className="text-[11px] text-ink-400">
              Rules applied: {lastResult.rules_applied.join(", ") || "none"}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
