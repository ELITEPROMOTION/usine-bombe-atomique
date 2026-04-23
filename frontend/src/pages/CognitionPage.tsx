import { useEffect, useState } from "react";
import { Brain } from "lucide-react";
import { Card, CardHeader, Badge, KPIWidget } from "@/design-system";
import { apiClient } from "@/api/client";

interface HealthReport { [k: string]: unknown }

export function CognitionPage() {
  const [health, setHealth] = useState<HealthReport | null>(null);
  const [circuit, setCircuit] = useState<unknown>(null);
  const [cache, setCache] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    try {
      const [h, c, ca] = await Promise.all([
        apiClient.get("/cognition/health/report").catch(() => ({ data: null })),
        apiClient.get("/cognition/circuit/recent").catch(() => ({ data: null })),
        apiClient.get("/cognition/cache/stats").catch(() => ({ data: null })),
      ]);
      setHealth(h.data);
      setCircuit(c.data);
      setCache(ca.data);
    } finally { setLoading(false); }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 30_000);
    return () => clearInterval(t);
  }, []);

  const techniques = [
    { id: "cot", name: "Chain of Thought", desc: "Raisonnement pas-a-pas" },
    { id: "tot", name: "Tree of Thoughts", desc: "Exploration arborescente" },
    { id: "got", name: "Graph of Thoughts", desc: "Graphe de raisonnement" },
    { id: "react", name: "ReAct", desc: "Reason + Act" },
    { id: "reflexion", name: "Reflexion", desc: "Pre-mortem + cycles" },
    { id: "mcts", name: "MCTS", desc: "Monte Carlo Tree Search" },
    { id: "debate", name: "Debate", desc: "Quorum experts" },
  ];

  return (
    <div className="px-4 lg:px-8 py-6 lg:py-10 max-w-7xl mx-auto">
      <div className="mb-6">
        <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300 mb-1 flex items-center gap-1.5">
          <Brain size={11} /> V5.4 Cognitive Reasoning
        </div>
        <h1 className="font-display text-2xl lg:text-3xl font-semibold">
          Cognition Live
        </h1>
        <p className="text-ink-300 text-sm mt-1">
          7 etages de raisonnement · Circuit breaker · Cache semantique
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <KPIWidget
          label="Techniques dispo"
          value={techniques.length}
          hint="CoT, ToT, GoT, ReAct, Reflexion, MCTS, Debate"
        />
        <KPIWidget
          label="Health report"
          value={loading ? "—" : health ? "OK" : "N/A"}
          status={health ? "success" : "neutral"}
        />
        <KPIWidget
          label="Circuit breaker"
          value={circuit ? "Active" : "OK"}
          status="success"
        />
        <KPIWidget
          label="Cache semantique"
          value={cache ? "En ligne" : "N/A"}
          status={cache ? "success" : "neutral"}
        />
      </div>

      <Card>
        <CardHeader
          icon={<Brain size={14} />}
          title="Techniques de raisonnement"
          hint="Catalogue V5.4"
        />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {techniques.map((t) => (
            <Card key={t.id} variant="outlined" padding="sm">
              <div className="flex items-center justify-between mb-1">
                <div className="text-sm font-medium text-ink-50">{t.name}</div>
                <Badge size="sm" status="success">active</Badge>
              </div>
              <div className="text-[11px] text-ink-400">{t.desc}</div>
            </Card>
          ))}
        </div>
      </Card>
    </div>
  );
}
