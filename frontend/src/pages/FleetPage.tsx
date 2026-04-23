import { Building2, TrendingUp } from "lucide-react";
import { Card, CardHeader, Badge, HealthDot, KPIWidget } from "@/design-system";

// 12 entites Dendani (seed statique - remplacer par backend/api/fleet.ts
// quand endpoint /api/v1/fleet/entities sera disponible)
const ENTITIES = [
  { id: "dendani-holding",     name: "Dendani Holding",        segment: "Holding",        autonomy: 94 },
  { id: "dendani-residences",  name: "Dendani Residences",     segment: "Immobilier",     autonomy: 91 },
  { id: "dendani-paie",        name: "Dendani Paie",           segment: "Services",       autonomy: 88 },
  { id: "dendani-compta",      name: "Dendani Comptabilite",   segment: "Services",       autonomy: 86 },
  { id: "dendani-hotel",       name: "Dendani Hotel",          segment: "Hospitalite",    autonomy: 83 },
  { id: "dendani-restaurant",  name: "Dendani Restaurant",     segment: "Hospitalite",    autonomy: 81 },
  { id: "dendani-logistique",  name: "Dendani Logistique",     segment: "Transport",      autonomy: 76 },
  { id: "dendani-batiment",    name: "Dendani Batiment",       segment: "Construction",   autonomy: 72 },
  { id: "dendani-agro",        name: "Dendani Agro",           segment: "Agriculture",    autonomy: 68 },
  { id: "dendani-import",      name: "Dendani Import",         segment: "Commerce",       autonomy: 65 },
  { id: "dendani-sante",       name: "Dendani Sante",          segment: "Sante",          autonomy: 54 },
  { id: "dendani-fondation",   name: "Dendani Fondation",      segment: "Social",         autonomy: 40 },
];

function health(autonomy: number) {
  if (autonomy >= 85) return "success" as const;
  if (autonomy >= 70) return "warning" as const;
  return "error" as const;
}

export function FleetPage() {
  const avg = Math.round(ENTITIES.reduce((s, e) => s + e.autonomy, 0) / ENTITIES.length);
  const top = [...ENTITIES].sort((a, b) => b.autonomy - a.autonomy)[0];
  const bottom = [...ENTITIES].sort((a, b) => a.autonomy - b.autonomy)[0];

  return (
    <div className="px-4 lg:px-8 py-6 lg:py-10 max-w-7xl mx-auto">
      <div className="mb-6">
        <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300 mb-1 flex items-center gap-1.5">
          <Building2 size={11} /> Fleet multi-entites
        </div>
        <h1 className="font-display text-2xl lg:text-3xl font-semibold">
          Groupe Dendani — {ENTITIES.length} entites
        </h1>
        <p className="text-ink-300 text-sm mt-1">
          Vue consolidee des scores d'autonomie et alertes cross-entity.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        <KPIWidget
          icon={<TrendingUp size={12} />}
          label="Score moyen"
          value={`${avg}%`}
          status={avg >= 85 ? "success" : avg >= 70 ? "warning" : "error"}
        />
        <KPIWidget
          label="Top autonomie"
          value={top.name}
          hint={`${top.autonomy}%`}
          status="success"
        />
        <KPIWidget
          label="A accompagner"
          value={bottom.name}
          hint={`${bottom.autonomy}%`}
          status={bottom.autonomy < 70 ? "warning" : "neutral"}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {ENTITIES.map((e) => (
          <Card key={e.id} padding="sm" className="hover:border-ink-600 transition">
            <div className="flex items-start justify-between gap-2 mb-2">
              <div>
                <div className="text-sm font-medium text-ink-50">{e.name}</div>
                <div className="text-[10px] uppercase tracking-[0.12em] text-ink-400">
                  {e.segment}
                </div>
              </div>
              <HealthDot status={health(e.autonomy)} animated={e.autonomy < 70} />
            </div>
            <div className="flex items-end justify-between">
              <div>
                <div className="text-2xl font-display font-semibold text-ink-50">
                  {e.autonomy}%
                </div>
                <div className="text-[10px] text-ink-400">autonomie</div>
              </div>
              <Badge status={health(e.autonomy)} size="sm">
                {e.autonomy >= 85 ? "Fiable" : e.autonomy >= 70 ? "Attention" : "Critique"}
              </Badge>
            </div>
            <div className="mt-2 h-1.5 bg-ink-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  e.autonomy >= 85 ? "bg-emerald-500"
                  : e.autonomy >= 70 ? "bg-yellow-500"
                  : "bg-red-500"
                }`}
                style={{ width: `${e.autonomy}%` }}
              />
            </div>
          </Card>
        ))}
      </div>

      <Card className="mt-6">
        <CardHeader
          title="Distribution par segment"
          hint="Moyenne d'autonomie par domaine d'activite"
        />
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-[0.14em] text-ink-400 border-b border-ink-800">
              <th className="py-2">Segment</th>
              <th className="py-2 text-right">Entites</th>
              <th className="py-2 text-right">Moyenne</th>
            </tr>
          </thead>
          <tbody>
            {Array.from(
              ENTITIES.reduce((m, e) => {
                const cur = m.get(e.segment) ?? { count: 0, sum: 0 };
                m.set(e.segment, { count: cur.count + 1, sum: cur.sum + e.autonomy });
                return m;
              }, new Map<string, {count: number; sum: number}>()).entries()
            ).map(([seg, v]) => {
              const avg = v.sum / v.count;
              return (
                <tr key={seg} className="border-b border-ink-800/40">
                  <td className="py-2 text-ink-100">{seg}</td>
                  <td className="py-2 text-right text-ink-300">{v.count}</td>
                  <td className="py-2 text-right">
                    <Badge status={avg >= 85 ? "success" : avg >= 70 ? "warning" : "error"}>
                      {avg.toFixed(0)}%
                    </Badge>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
