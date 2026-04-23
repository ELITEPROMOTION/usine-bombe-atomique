import { useEffect } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Wifi, WifiOff, Layers, FileCode2, ArrowRight } from "lucide-react";
import clsx from "clsx";
import { useTaskStream } from "@/hooks/useTaskStream";
import { StatusChip } from "@/components/ui/StatusChip";
import { ScoreRing } from "@/components/ui/ScoreRing";

const ALL_AGENTS = [
  { id: "agent-01-claude-code", label: "Claude Code",   order: 1 },
  { id: "agent-14-linter",      label: "Code Linter",   order: 2 },
  { id: "agent-02-sonarqube",   label: "SonarQube",     order: 2 },
  { id: "agent-04-pytest",      label: "Pytest",        order: 2 },
  { id: "agent-21-readme",      label: "README Gen",    order: 2 },
];

export function ProgressPage() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const { snap, connected, error } = useTaskStream(id);

  useEffect(() => {
    if (!snap) return;
    if (["completed", "failed"].includes(snap.task.status)) {
      const t = setTimeout(() => nav(`/tasks/${id}/results`, { replace: false }), 600);
      return () => clearTimeout(t);
    }
  }, [snap, id, nav]);

  const agentsByStatus = new Map<string, { status: string; duration_ms: number | null; agent_name: string }>();
  snap?.agents.forEach((a) => agentsByStatus.set(a.agent_id, { status: a.status, duration_ms: a.duration_ms, agent_name: a.agent_name }));

  return (
    <div className="px-6 lg:px-10 py-10 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        className="flex items-start justify-between flex-wrap gap-4 mb-8">
        <div>
          <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300/90 mb-1 flex items-center gap-2">
            Pipeline temps reel
            {connected
              ? <span className="chip-success"><Wifi size={10}/> Live</span>
              : <span className="chip-neutral"><WifiOff size={10}/> Connexion...</span>
            }
          </div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">
            Generation en cours
          </h1>
          <p className="text-ink-300 text-sm mt-1 font-mono">ID · {id?.slice(0, 8)}</p>
        </div>
        <div className="flex items-center gap-4">
          <ScoreRing score={snap?.task.validation_score ?? 0} label="Score" />
          <StatusChip status={snap?.task.status ?? "pending"} />
        </div>
      </motion.div>

      {error && (
        <div className="mb-6 text-sm text-danger bg-danger/10 border border-danger/30 rounded-lg px-4 py-3">
          Erreur flux temps reel : {error}
        </div>
      )}

      <div className="grid lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3">
          <div className="panel p-6">
            <div className="flex items-center justify-between mb-5">
              <div>
                <div className="text-[11px] uppercase tracking-[0.18em] text-ink-400">DAG orchestre</div>
                <h2 className="font-medium text-ink-50 mt-0.5">Agents actifs</h2>
              </div>
              <span className="chip-gold"><Layers size={11}/> 2 vagues · parallele</span>
            </div>

            <Wave title="Vague 1 · Generation" items={ALL_AGENTS.filter(a => a.order === 1)} getState={(id) => agentsByStatus.get(id)} />
            <div className="my-5 flex items-center gap-3 text-ink-500">
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-ink-700 to-transparent" />
              <span className="text-[10px] uppercase tracking-[0.22em]">then</span>
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-ink-700 to-transparent" />
            </div>
            <Wave title="Vague 2 · Analyse + Tests + Doc (parallele)" items={ALL_AGENTS.filter(a => a.order === 2)} getState={(id) => agentsByStatus.get(id)} />
          </div>
        </div>

        <div className="lg:col-span-2 space-y-6">
          <div className="panel p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="text-[11px] uppercase tracking-[0.18em] text-ink-400">Validation 5 niveaux</div>
                <h2 className="font-medium text-ink-50 mt-0.5">Pipeline CDC Ch.7</h2>
              </div>
            </div>
            <div className="space-y-3">
              {(snap?.validation.length ? snap.validation : placeholderLevels()).map((v) => (
                <ValidationRow key={v.level} level={v.level} name={v.name} score={v.score} passed={v.passed} />
              ))}
            </div>
          </div>

          <div className="panel p-6">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[11px] uppercase tracking-[0.18em] text-ink-400">Artefacts</div>
                <div className="font-medium text-ink-50 mt-0.5">Fichiers produits</div>
              </div>
              <div className="flex items-center gap-2">
                <FileCode2 size={16} className="text-gold-300" />
                <span className="text-2xl font-semibold tabular-nums">{snap?.artifacts_count ?? 0}</span>
              </div>
            </div>
            {snap && ["completed","failed"].includes(snap.task.status) && (
              <Link to={`/tasks/${id}/results`} className="btn-primary w-full mt-4">
                Voir les resultats <ArrowRight size={14}/>
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Wave({
  title,
  items,
  getState,
}: {
  title: string;
  items: { id: string; label: string }[];
  getState: (id: string) => { status: string; duration_ms: number | null; agent_name: string } | undefined;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.18em] text-ink-400 mb-3">{title}</div>
      <div className="grid sm:grid-cols-2 gap-3">
        {items.map((it) => {
          const state = getState(it.id);
          const status = state?.status ?? "pending";
          const running = ["running", "executing"].includes(status);
          return (
            <div
              key={it.id}
              className={clsx(
                "panel-inner p-3.5 flex items-center gap-3 transition-all overflow-hidden",
                running && "border-gold-500/50",
                status === "success" && "border-success/30",
                status === "failed" && "border-danger/40",
              )}
            >
              <div className={clsx(
                "w-2 h-2 rounded-full shrink-0",
                status === "success" ? "bg-success"
                  : status === "failed" ? "bg-danger"
                  : running ? "bg-gold-300 animate-pulse-soft"
                  : "bg-ink-500"
              )}/>
              <div className="flex-1 min-w-0">
                <div className="text-sm text-ink-50 truncate">{it.label}</div>
                <div className="text-[11px] text-ink-400 font-mono">{it.id}</div>
              </div>
              <div className="text-right">
                <StatusChip status={status} compact />
                {state?.duration_ms != null && (
                  <div className="text-[10px] text-ink-400 mt-1 tabular-nums">
                    {(state.duration_ms / 1000).toFixed(1)}s
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ValidationRow({ level, name, score, passed }: { level: number; name: string; score: number; passed: boolean }) {
  const pct = Math.max(0, Math.min(1, score)) * 100;
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2 text-ink-200">
          <span className="text-ink-400 tabular-nums">L{level}</span>
          <span>{name}</span>
        </div>
        <div className="flex items-center gap-2 tabular-nums">
          <span className={passed ? "text-success" : "text-danger"}>{pct.toFixed(1)}%</span>
        </div>
      </div>
      <div className="mt-1.5 h-1.5 bg-ink-800 rounded-full overflow-hidden">
        <div
          className={clsx(
            "h-full rounded-full transition-all duration-700 ease-out",
            passed
              ? "bg-gradient-to-r from-gold-300 to-gold-500"
              : "bg-gradient-to-r from-danger/70 to-danger"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function placeholderLevels() {
  return [
    { level: 1, name: "Coherence Logique",      score: 0, passed: false },
    { level: 2, name: "Conformite CDC",         score: 0, passed: false },
    { level: 3, name: "Qualite (Lint + Sonar)", score: 0, passed: false },
    { level: 4, name: "Tests (Pytest)",         score: 0, passed: false },
    { level: 5, name: "Production Ready",       score: 0, passed: false },
  ];
}
