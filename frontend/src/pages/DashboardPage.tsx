import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowUpRight, Sparkles, Activity, Gauge, CheckCircle2 } from "lucide-react";
import { listTasks, type Task } from "@/api/tasks";
import { StatusChip } from "@/components/ui/StatusChip";

export function DashboardPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listTasks(20).then((t) => { setTasks(t); setLoading(false); });
  }, []);

  const completed = tasks.filter((t) => t.status === "completed");
  const avgScore = completed.length
    ? completed.reduce((s, t) => s + Number(t.validation_score), 0) / completed.length
    : 0;
  const successRate = tasks.length
    ? Math.round((completed.length / tasks.length) * 100)
    : 0;

  return (
    <div className="px-6 lg:px-10 py-10 max-w-7xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        className="flex items-end justify-between mb-8"
      >
        <div>
          <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300/90 mb-1">Orchestration</div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Tableau de bord</h1>
          <p className="text-ink-300 text-sm mt-1">
            Suivi des generations, scores de validation, et statut des 23 agents.
          </p>
        </div>
        <Link to="/new" className="btn-primary"><Sparkles size={15} /> Nouveau projet</Link>
      </motion.div>

      <div className="grid md:grid-cols-3 gap-4 mb-10">
        <KpiCard
          icon={<Activity size={15} className="text-gold-300" />}
          label="Taches totales"
          value={tasks.length.toString()}
          trend={tasks.length > 0 ? "actif" : "idle"}
        />
        <KpiCard
          icon={<Gauge size={15} className="text-gold-300" />}
          label="Score moyen"
          value={`${(avgScore * 100).toFixed(1)}%`}
          trend="validation"
        />
        <KpiCard
          icon={<CheckCircle2 size={15} className="text-gold-300" />}
          label="Taux de reussite"
          value={`${successRate}%`}
          trend={`${completed.length}/${tasks.length}`}
        />
      </div>

      <div className="panel overflow-hidden">
        <div className="px-6 py-4 hairline flex items-center justify-between">
          <div>
            <h2 className="font-medium text-ink-50">Dernieres generations</h2>
            <p className="text-xs text-ink-400 mt-0.5">Historique recent · cliquer pour suivre en direct</p>
          </div>
          <Link to="/projects" className="text-xs text-gold-300 hover:text-gold-200 inline-flex items-center gap-1">
            Tout voir <ArrowUpRight size={12} />
          </Link>
        </div>
        <div className="divide-y divide-ink-800/80">
          {loading && (
            <div className="px-6 py-8 text-center text-ink-400 text-sm">Chargement...</div>
          )}
          {!loading && tasks.length === 0 && (
            <div className="px-6 py-12 text-center">
              <div className="text-ink-300 text-sm mb-3">Aucune generation pour le moment.</div>
              <Link to="/new" className="btn-primary"><Sparkles size={14}/> Lancer la premiere</Link>
            </div>
          )}
          {tasks.map((t) => (
            <Link
              key={t.id}
              to={`/tasks/${t.id}`}
              className="px-6 py-4 flex items-center gap-4 hover:bg-ink-800/40 transition-colors group"
            >
              <div className="flex-1 min-w-0">
                <div className="text-sm text-ink-50 truncate">{t.prompt.split("\n")[0].slice(0, 90)}</div>
                <div className="text-[11px] text-ink-400 mt-1 font-mono">
                  {t.id.slice(0, 8)} · {new Date(t.created_at).toLocaleString("fr-FR")}
                </div>
              </div>
              <div className="text-right tabular-nums text-sm text-ink-200 hidden md:block">
                {(Number(t.validation_score) * 100).toFixed(1)}%
              </div>
              <StatusChip status={t.status} />
              <ArrowUpRight size={14} className="text-ink-400 group-hover:text-gold-300 transition" />
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

function KpiCard({ icon, label, value, trend }: { icon: React.ReactNode; label: string; value: string; trend: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      className="panel p-5"
    >
      <div className="flex items-center gap-2 text-ink-300 text-xs uppercase tracking-[0.18em]">
        {icon} {label}
      </div>
      <div className="mt-3 text-3xl font-semibold tracking-tight text-ink-50 tabular-nums">{value}</div>
      <div className="text-xs text-ink-400 mt-1">{trend}</div>
    </motion.div>
  );
}
