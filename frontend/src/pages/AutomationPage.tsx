import { useEffect, useMemo, useState } from "react";
import {
  Zap, Clock, CheckCircle2, XCircle, Pause, Play, AlertTriangle,
  RefreshCw, Calendar,
} from "lucide-react";
import {
  Card, CardHeader, Badge, HealthDot, KPIWidget, Timeline,
  AlertBanner, ActionButton,
} from "@/design-system";
import {
  getScheduled, getHistory, getMetrics, getFailures,
  pauseTask, resumeTask, triggerTask,
  type WorkflowSchedule, type WorkflowRun, type WorkflowMetrics,
} from "@/api/workflows";

function fmt(ms: number | null) {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}min`;
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60_000);
  if (min < 1) return "a l'instant";
  if (min < 60) return `il y a ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `il y a ${h}h`;
  return `il y a ${Math.floor(h / 24)}j`;
}

const TIER_LABEL: Record<number, string> = {
  1: "Critique (monitoring)",
  2: "Securite",
  3: "Optimisation",
  4: "Memoire",
  5: "BI Reports",
  6: "Veille",
  7: "Backup",
};

export function AutomationPage() {
  const [schedules, setSchedules] = useState<WorkflowSchedule[]>([]);
  const [history, setHistory] = useState<WorkflowRun[]>([]);
  const [metrics, setMetrics] = useState<WorkflowMetrics | null>(null);
  const [failures, setFailures] = useState<{failures: any[]; dlq: any[]}>({ failures: [], dlq: [] });
  const [busy, setBusy] = useState<string | null>(null);
  const [filter, setFilter] = useState<number | "all">("all");

  async function refresh() {
    try {
      const [s, h, m, f] = await Promise.all([
        getScheduled(),
        getHistory(30),
        getMetrics(7),
        getFailures(10),
      ]);
      setSchedules(s.schedules);
      setHistory(h.runs);
      setMetrics(m);
      setFailures(f);
    } catch (e) { console.error(e); }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 30_000);
    return () => clearInterval(t);
  }, []);

  async function handleTrigger(name: string) {
    setBusy(name);
    try {
      await triggerTask(name);
      await refresh();
    } finally { setBusy(null); }
  }

  async function handleToggle(s: WorkflowSchedule) {
    setBusy(s.task_name);
    try {
      if (s.enabled) await pauseTask(s.task_name);
      else await resumeTask(s.task_name);
      await refresh();
    } finally { setBusy(null); }
  }

  const visibleSchedules = schedules.filter(
    (s) => filter === "all" || s.tier === filter,
  );

  const total = metrics?.total_runs ?? 0;
  const succ = metrics?.total_success ?? 0;
  const fail = metrics?.total_failure ?? 0;
  const rate = metrics?.global_success_rate ?? 1;

  const runningCount = history.filter((r) => r.status === "running").length;

  const timelineItems = useMemo(() => history.slice(0, 10).map((r) => ({
    id: r.run_id,
    title: r.task_name,
    description: r.error ?? `${r.trigger_kind} · tries=${r.tries}`,
    time: timeAgo(r.started_at),
    status: r.status === "succeeded" ? "success" as const
         : r.status === "failed" ? "error" as const
         : r.status === "timeout" ? "warning" as const
         : r.status === "dead_letter" ? "error" as const
         : "info" as const,
    badges: <Badge size="sm" status={
      r.status === "succeeded" ? "success"
      : r.status === "failed" ? "error"
      : r.status === "timeout" ? "warning"
      : "info"
    }>{fmt(r.duration_ms)}</Badge>,
  })), [history]);

  return (
    <div className="px-4 lg:px-8 py-6 lg:py-10 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300 mb-1 flex items-center gap-1.5">
            <Zap size={11} /> V5.5 Automation
          </div>
          <h1 className="font-display text-2xl lg:text-3xl font-semibold">
            Automation Live
          </h1>
          <p className="text-ink-300 text-sm mt-1">
            26 tasks cron + 9 event triggers + 2 workers redondants
          </p>
        </div>
        <ActionButton
          variant="secondary" size="sm" onClick={refresh}
          leading={<RefreshCw size={13} />}
        >
          Rafraichir
        </ActionButton>
      </div>

      {failures.dlq.length > 0 && (
        <div className="mb-6">
          <AlertBanner
            status="warning"
            title={`${failures.dlq.length} entree(s) dans Dead Letter Queue non resolue(s)`}
          >
            Verifier les taches ayant echoue 3x et traiter manuellement.
          </AlertBanner>
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <KPIWidget
          icon={<Clock size={12} />}
          label="Tasks programmees"
          value={schedules.length}
          hint={`26 attendues`}
          status={schedules.length === 26 ? "success" : "warning"}
        />
        <KPIWidget
          icon={<Play size={12} />}
          label="En cours"
          value={runningCount}
          hint={`30 derniers runs`}
          status={runningCount > 0 ? "info" : "neutral"}
        />
        <KPIWidget
          icon={<CheckCircle2 size={12} />}
          label="Taux succes (7j)"
          value={`${(rate * 100).toFixed(1)}%`}
          deltaLabel={`${succ} OK / ${fail} KO`}
          status={rate >= 0.95 ? "success" : rate >= 0.85 ? "warning" : "error"}
        />
        <KPIWidget
          icon={<XCircle size={12} />}
          label="DLQ pending"
          value={failures.dlq.length}
          hint={`${failures.failures.length} echecs visibles`}
          status={failures.dlq.length === 0 ? "success" : "warning"}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader
            icon={<Calendar size={14} />}
            title="Schedules par tier"
            hint={`${visibleSchedules.length} visibles / ${schedules.length}`}
            action={
              <div className="flex gap-1 flex-wrap">
                <TierPill label="Toutes" active={filter === "all"} onClick={() => setFilter("all")} />
                {[1,2,3,4,5,6,7].map((t) => (
                  <TierPill key={t} label={`T${t}`} active={filter === t} onClick={() => setFilter(t)} />
                ))}
              </div>
            }
          />
          <div className="divide-y divide-ink-800/60 -mx-2 max-h-[400px] overflow-y-auto">
            {visibleSchedules.map((s) => (
              <div key={s.task_name} className="px-2 py-2.5 flex items-center gap-3">
                <HealthDot
                  status={s.enabled ? "success" : "neutral"}
                  animated={s.enabled}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-ink-100 truncate">
                    {s.task_name}
                  </div>
                  <div className="text-[11px] text-ink-400 truncate">
                    T{s.tier} · {s.cron_expression} · {s.description}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <ActionButton
                    size="sm" variant="ghost"
                    disabled={busy === s.task_name}
                    onClick={() => handleTrigger(s.task_name)}
                    title="Trigger manuel"
                  >
                    <Zap size={12} /> Run
                  </ActionButton>
                  <ActionButton
                    size="sm"
                    variant={s.enabled ? "ghost" : "secondary"}
                    disabled={busy === s.task_name}
                    onClick={() => handleToggle(s)}
                    title={s.enabled ? "Pause" : "Reprendre"}
                  >
                    {s.enabled ? <Pause size={12} /> : <Play size={12} />}
                  </ActionButton>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <CardHeader
            icon={<Clock size={14} />}
            title="Executions recentes"
            hint={`${history.length} derniers runs`}
          />
          <div className="max-h-[400px] overflow-y-auto pr-1">
            <Timeline items={timelineItems} compact />
          </div>
        </Card>
      </div>

      {failures.failures.length > 0 && (
        <Card className="mt-6">
          <CardHeader
            icon={<AlertTriangle size={14} />}
            title="Echecs recents"
            hint={`${failures.failures.length} derniers`}
          />
          <div className="space-y-2 text-sm">
            {failures.failures.slice(0, 5).map((f: any) => (
              <div key={f.run_id} className="p-2 bg-red-500/5 border border-red-500/20 rounded-md">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-red-200">{f.task_name}</span>
                  <span className="text-[10px] text-ink-400">
                    {timeAgo(f.started_at)} · {f.tries}x
                  </span>
                </div>
                <div className="text-[11px] text-ink-300 mt-1 truncate">
                  {f.error}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function TierPill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={[
        "px-2 py-0.5 text-[10px] rounded border transition",
        active
          ? "bg-gold-400/20 border-gold-400/40 text-gold-200"
          : "bg-ink-800/60 border-ink-700/40 text-ink-300 hover:text-ink-100",
      ].join(" ")}
    >
      {label}
    </button>
  );
}
