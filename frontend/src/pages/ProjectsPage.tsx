import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowUpRight, Sparkles } from "lucide-react";
import { listTasks, type Task } from "@/api/tasks";
import { StatusChip } from "@/components/ui/StatusChip";

export function ProjectsPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listTasks(100).then((t) => { setTasks(t); setLoading(false); });
  }, []);

  return (
    <div className="px-6 lg:px-10 py-10 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex items-end justify-between mb-8">
        <div>
          <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300/90 mb-1">Historique</div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Tous les projets</h1>
          <p className="text-ink-300 text-sm mt-1">{tasks.length} generations enregistrees</p>
        </div>
        <Link to="/new" className="btn-primary"><Sparkles size={15}/> Nouveau projet</Link>
      </motion.div>

      <div className="panel overflow-hidden">
        <div className="grid grid-cols-[1fr_140px_110px_120px_40px] px-5 py-3 text-[11px] uppercase tracking-[0.18em] text-ink-400 border-b border-ink-800 hidden md:grid">
          <span>Specification</span>
          <span>Cree</span>
          <span className="tabular-nums">Score</span>
          <span>Statut</span>
          <span></span>
        </div>
        {loading && <div className="p-6 text-center text-ink-400 text-sm">Chargement...</div>}
        {!loading && tasks.length === 0 && (
          <div className="p-10 text-center text-ink-400 text-sm">
            Aucun projet. <Link to="/new" className="text-gold-300 hover:text-gold-200">Lancer le premier</Link>.
          </div>
        )}
        {tasks.map((t) => (
          <Link
            key={t.id}
            to={`/tasks/${t.id}${t.status === "completed" || t.status === "failed" ? "/results" : ""}`}
            className="grid md:grid-cols-[1fr_140px_110px_120px_40px] grid-cols-1 gap-2 md:gap-0 px-5 py-4 hover:bg-ink-800/40 transition-colors border-b border-ink-800/70 group"
          >
            <div className="min-w-0">
              <div className="text-sm text-ink-100 truncate">{t.prompt.split("\n")[0].slice(0, 110)}</div>
              <div className="text-[11px] text-ink-500 font-mono mt-1">{t.id.slice(0, 8)}</div>
            </div>
            <div className="text-xs text-ink-300">{new Date(t.created_at).toLocaleDateString("fr-FR")}</div>
            <div className="text-sm tabular-nums text-ink-100">{(Number(t.validation_score) * 100).toFixed(1)}%</div>
            <div><StatusChip status={t.status}/></div>
            <div className="flex justify-end"><ArrowUpRight size={14} className="text-ink-500 group-hover:text-gold-300 transition"/></div>
          </Link>
        ))}
      </div>
    </div>
  );
}
