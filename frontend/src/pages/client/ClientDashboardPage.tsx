import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Sparkles, Building2, Calendar, AlertCircle,
  Activity as ActivityIcon, Receipt, Package, MessageSquare, Hammer,
} from "lucide-react";
import {
  getClientActivity,
  getClientMilestones,
  getClientProject,
  type ClientActivity,
  type ClientMilestone,
  type ClientProject,
} from "@/api/client_dashboard";
import { listClientHandoffs, type ClientHandoff } from "@/api/client_payments";
import { MilestoneTimeline, ProgressGauge } from "@/design-system";

const ACTIVITY_ICONS = {
  build: Hammer,
  payment: Receipt,
  deliverable: Package,
  handoff: AlertCircle,
  comms: MessageSquare,
} as const;

export function ClientDashboardPage() {
  const [project, setProject] = useState<ClientProject | null>(null);
  const [milestones, setMilestones] = useState<ClientMilestone[]>([]);
  const [activity, setActivity] = useState<ClientActivity[]>([]);
  const [handoffs, setHandoffs] = useState<ClientHandoff[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      getClientProject(),
      getClientMilestones(),
      getClientActivity(8),
      listClientHandoffs(),
    ]).then(([p, m, a, h]) => {
      setProject(p);
      setMilestones(m);
      setActivity(a);
      setHandoffs(h);
      setLoading(false);
    });
  }, []);

  if (loading || !project) {
    return (
      <div className="px-6 lg:px-10 py-10 max-w-7xl mx-auto text-ink-400 text-sm">
        Chargement de votre espace...
      </div>
    );
  }

  const pendingHandoffs = handoffs.filter(
    (h) => h.status === "requested" || h.status === "notified",
  );

  return (
    <div className="px-6 lg:px-10 py-10 max-w-7xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        className="flex flex-wrap items-end justify-between gap-4 mb-8"
      >
        <div>
          <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300/90 mb-1">
            Votre projet
          </div>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink-50">
            {project.company_name}
          </h1>
          <p className="text-ink-300 text-sm mt-1 inline-flex items-center gap-2">
            <Sparkles size={14} className="text-gold-300" />
            {project.pack_name} · livraison estimee le{" "}
            <span className="text-ink-100 font-medium">
              {new Date(project.estimated_delivery_at).toLocaleDateString(
                "fr-FR", { day: "2-digit", month: "long", year: "numeric" },
              )}
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-ink-400">
          <Building2 size={12} /> Client #{project.project_id.slice(0, 8)}
        </div>
      </motion.div>

      {pendingHandoffs.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
          className="panel p-5 mb-8 border-warn/40 bg-warn/5"
        >
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-lg bg-warn/15 border border-warn/40 flex items-center justify-center text-warn">
              <AlertCircle size={18} />
            </div>
            <div className="flex-1">
              <h3 className="font-medium text-ink-50 tracking-tight">
                {pendingHandoffs.length} action
                {pendingHandoffs.length > 1 ? "s" : ""} en attente
              </h3>
              <ul className="mt-2 text-sm text-ink-200 space-y-1">
                {pendingHandoffs.slice(0, 3).map((h) => (
                  <li key={h.id} className="flex items-center gap-2">
                    <span className="w-1 h-1 rounded-full bg-warn" />
                    {h.title}
                    <span className="text-[11px] text-ink-400 ml-2">
                      avant le{" "}
                      {new Date(h.due_at).toLocaleDateString(
                        "fr-FR", { day: "2-digit", month: "short" },
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </motion.div>
      )}

      <div className="grid lg:grid-cols-[auto_1fr] gap-6 mb-10">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
          className="panel p-8 flex flex-col items-center justify-center"
        >
          <ProgressGauge
            value={project.progress_pct}
            sublabel="Avancement"
            size="lg"
          />
          <div className="mt-5 text-center">
            <div className="text-[10px] uppercase tracking-[0.22em] text-gold-300/90">
              Prochaine etape
            </div>
            <div className="font-medium text-ink-50 mt-1 tracking-tight">
              {project.next_milestone}
            </div>
            <div className="text-[11px] text-ink-400 mt-0.5 inline-flex items-center gap-1">
              <Calendar size={11} />
              {new Date(project.next_milestone_due_at).toLocaleDateString(
                "fr-FR", { day: "2-digit", month: "long" },
              )}
            </div>
          </div>
        </motion.div>

        <div className="panel p-6">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="font-medium text-ink-50 tracking-tight">
                Plan de production
              </h2>
              <p className="text-xs text-ink-400 mt-0.5">
                Etapes definies au cadrage. Mises a jour en temps reel.
              </p>
            </div>
          </div>
          <MilestoneTimeline items={milestones} />
        </div>
      </div>

      <div className="panel overflow-hidden">
        <div className="px-6 py-4 hairline flex items-center gap-3">
          <ActivityIcon size={14} className="text-gold-300" />
          <div>
            <h2 className="font-medium text-ink-50">Activite recente</h2>
            <p className="text-xs text-ink-400 mt-0.5">
              Tout ce qui se passe sur votre projet, en transparence.
            </p>
          </div>
        </div>
        <ul className="divide-y divide-ink-800/80">
          {activity.map((a) => {
            const Icon = ACTIVITY_ICONS[a.kind];
            return (
              <li key={a.id} className="px-6 py-4 flex items-start gap-4">
                <div className="w-8 h-8 rounded-md bg-ink-800/60 border border-ink-700/60 flex items-center justify-center text-ink-200 shrink-0">
                  <Icon size={14} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-ink-50">{a.title}</div>
                  {a.detail && (
                    <div className="text-[11px] text-ink-400 mt-0.5">
                      {a.detail}
                    </div>
                  )}
                </div>
                <div className="text-[11px] text-ink-400 tabular-nums shrink-0">
                  {new Date(a.at).toLocaleDateString("fr-FR", {
                    day: "2-digit", month: "short",
                  })}
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
