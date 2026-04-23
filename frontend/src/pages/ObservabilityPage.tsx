import { useEffect, useState } from "react";
import { Activity, Search, Filter } from "lucide-react";
import {
  Card, CardHeader, Badge, HealthDot, KPIWidget,
} from "@/design-system";
import { apiClient } from "@/api/client";

interface AuditEvent {
  event_id: string;
  actor: string;
  action: string;
  created_at: string;
  payload?: unknown;
}

export function ObservabilityPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [filter, setFilter] = useState("");
  const [actionFilter, setActionFilter] = useState("");

  async function refresh() {
    try {
      const r = await apiClient.get("/analytics/audit/tail?limit=100" +
        (actionFilter ? `&action=${encodeURIComponent(actionFilter)}` : ""));
      setEvents(r.data as AuditEvent[]);
    } catch (e) { console.error(e); }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10_000);
    return () => clearInterval(t);
  }, [actionFilter]);

  const visible = events.filter((e) => {
    if (!filter) return true;
    const q = filter.toLowerCase();
    return e.actor.toLowerCase().includes(q) ||
           e.action.toLowerCase().includes(q);
  });

  const failureRate = events.filter((e) => e.action.includes("failed")).length / Math.max(events.length, 1);
  const successRate = 1 - failureRate;

  return (
    <div className="px-4 lg:px-8 py-6 lg:py-10 max-w-7xl mx-auto">
      <div className="mb-6">
        <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300 mb-1 flex items-center gap-1.5">
          <Activity size={11} /> Observabilite
        </div>
        <h1 className="font-display text-2xl lg:text-3xl font-semibold">
          Stream audit live
        </h1>
        <p className="text-ink-300 text-sm mt-1">
          Tail en temps reel des evenements du systeme (refresh 10s).
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <KPIWidget
          icon={<Activity size={12} />}
          label="Events visibles"
          value={visible.length}
          hint={`${events.length} derniers`}
        />
        <KPIWidget
          label="Taux succes"
          value={`${(successRate * 100).toFixed(0)}%`}
          status={successRate >= 0.95 ? "success" : successRate >= 0.85 ? "warning" : "error"}
        />
        <KPIWidget
          label="Actions uniques"
          value={new Set(events.map((e) => e.action)).size}
        />
        <KPIWidget
          label="Acteurs uniques"
          value={new Set(events.map((e) => e.actor)).size}
        />
      </div>

      <Card>
        <CardHeader
          icon={<Filter size={14} />}
          title="Filtres"
          action={
            <div className="flex gap-2 items-center flex-wrap">
              <div className="relative">
                <Search size={12} className="absolute left-2 top-1.5 text-ink-400" />
                <input
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Recherche acteur/action..."
                  className="pl-7 pr-2 py-1 text-xs bg-ink-800 border border-ink-700 rounded-md text-ink-100 placeholder:text-ink-500 focus:outline-none focus:border-gold-400/50"
                />
              </div>
              <select
                value={actionFilter}
                onChange={(e) => setActionFilter(e.target.value)}
                className="px-2 py-1 text-xs bg-ink-800 border border-ink-700 rounded-md text-ink-100 focus:outline-none"
              >
                <option value="">Toutes actions</option>
                <option value="workflow_task_failed">workflow_task_failed</option>
                <option value="autonomy_decision">autonomy_decision</option>
                <option value="login">login</option>
              </select>
            </div>
          }
        />
        <div className="space-y-1.5 max-h-[600px] overflow-y-auto font-mono text-[11px]">
          {visible.length === 0 && (
            <div className="text-ink-400 py-6 text-center italic">
              Aucun evenement.
            </div>
          )}
          {visible.map((e) => (
            <div
              key={e.event_id}
              className="px-2 py-1.5 rounded hover:bg-ink-800/50 flex items-start gap-2 border-l-2 border-transparent hover:border-gold-400/40"
            >
              <HealthDot
                status={
                  e.action.includes("failed") || e.action.includes("error") ? "error"
                  : e.action.includes("warn") ? "warning"
                  : e.action.includes("login") ? "info"
                  : "success"
                }
                size="sm"
              />
              <span className="text-ink-500 shrink-0">
                {new Date(e.created_at).toISOString().substring(11, 19)}
              </span>
              <Badge size="sm" status="neutral">{e.action}</Badge>
              <span className="text-ink-300 truncate flex-1" title={e.actor}>
                {e.actor}
              </span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
