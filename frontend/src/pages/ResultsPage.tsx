import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Download, FileDown, CheckCircle2, AlertTriangle, ArrowLeft, Copy, FileCode2, Package } from "lucide-react";
import clsx from "clsx";
import {
  getTask, listArtifacts, listExecutions, getValidation, getArtifact, taskZipUrl, artifactDownloadUrl,
  type Task, type ArtifactMeta, type AgentExecution, type ValidationLevel, type ArtifactContent,
} from "@/api/tasks";
import { StatusChip } from "@/components/ui/StatusChip";
import { ScoreRing } from "@/components/ui/ScoreRing";

export function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const [task, setTask] = useState<Task | null>(null);
  const [agents, setAgents] = useState<AgentExecution[]>([]);
  const [validation, setValidation] = useState<ValidationLevel[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactMeta[]>([]);
  const [selected, setSelected] = useState<ArtifactContent | null>(null);

  useEffect(() => {
    if (!id) return;
    Promise.all([getTask(id), listExecutions(id), getValidation(id), listArtifacts(id)])
      .then(([t, e, v, a]) => { setTask(t); setAgents(e); setValidation(v); setArtifacts(a); });
  }, [id]);

  async function preview(m: ArtifactMeta) {
    if (!id) return;
    const content = await getArtifact(id, m.id);
    setSelected(content);
  }

  const verdict = deriveVerdict(validation, task?.validation_score ?? 0);
  const score = task?.validation_score ?? 0;

  return (
    <div className="px-6 lg:px-10 py-10 max-w-7xl mx-auto">
      <div className="flex items-center gap-3 mb-6 text-sm text-ink-400">
        <Link to="/" className="hover:text-gold-300 inline-flex items-center gap-1"><ArrowLeft size={12}/> Dashboard</Link>
        <span>/</span>
        <span className="text-ink-200 font-mono">{id?.slice(0, 8)}</span>
      </div>

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        className={clsx(
          "panel p-6 lg:p-8 mb-6 flex flex-col lg:flex-row items-start lg:items-center gap-6 lg:gap-8",
          verdict === "PASS" && "ring-1 ring-gold-500/30",
          verdict === "HARD_FAIL" && "ring-1 ring-danger/30",
        )}
      >
        <ScoreRing score={score} size={136} label="Validation" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={clsx(
              "text-[11px] uppercase tracking-[0.28em]",
              verdict === "PASS" ? "text-gold-300" :
              verdict === "CONDITIONAL_PASS" ? "text-warn" :
              verdict === "SOFT_FAIL" ? "text-warn" : "text-danger",
            )}>{verdict.replace("_", " ")}</span>
            {task && <StatusChip status={task.status} />}
          </div>
          <h1 className="font-display text-3xl font-semibold tracking-tight mb-2">
            {verdict === "PASS" || verdict === "CONDITIONAL_PASS"
              ? "Livrable pret au deploiement"
              : "Livrable incomplet"}
          </h1>
          <p className="text-ink-300 text-sm line-clamp-2 max-w-3xl">
            {task?.prompt.split("\n")[0]}
          </p>
          <div className="flex flex-wrap items-center gap-4 mt-4 text-xs text-ink-400">
            <span>Cree le {task && new Date(task.created_at).toLocaleString("fr-FR")}</span>
            <span>·</span>
            <span>{artifacts.length} artefacts</span>
            <span>·</span>
            <span>{agents.length} agents executes</span>
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <a
            href={taskZipUrl(id || "")}
            className="btn-primary"
            download
          >
            <Package size={14} /> Telecharger .zip
          </a>
          <Link to="/new" className="btn-outline">
            Nouveau projet
          </Link>
        </div>
      </motion.div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="panel p-5 lg:col-span-1">
          <div className="text-[11px] uppercase tracking-[0.18em] text-ink-400 mb-3">Validation 5 niveaux</div>
          <div className="space-y-3">
            {validation.map((v) => (
              <div key={v.level} className="flex items-start gap-3">
                <div className={clsx(
                  "w-7 h-7 rounded-md flex items-center justify-center shrink-0 text-[11px] font-semibold tabular-nums",
                  v.passed ? "bg-success/10 text-success border border-success/30"
                            : "bg-danger/10 text-danger border border-danger/30",
                )}>
                  {v.passed ? <CheckCircle2 size={13}/> : <AlertTriangle size={13}/>}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-ink-50">{v.name}</div>
                  <div className="text-[11px] text-ink-400 mt-0.5 truncate">{v.details}</div>
                </div>
                <div className="text-sm tabular-nums text-ink-100">{(v.score * 100).toFixed(1)}%</div>
              </div>
            ))}
          </div>
          <div className="divider my-5" />
          <div className="text-[11px] uppercase tracking-[0.18em] text-ink-400 mb-3">Agents</div>
          <div className="space-y-2.5">
            {agents.map((a) => (
              <div key={a.id} className="flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-ink-100 truncate">{a.agent_name}</div>
                  <div className="text-[11px] text-ink-400 font-mono truncate">{a.agent_id}</div>
                </div>
                <div className="text-[11px] text-ink-300 tabular-nums">
                  {a.duration_ms ? `${(a.duration_ms / 1000).toFixed(1)}s` : "—"}
                </div>
                <StatusChip status={a.status} compact />
              </div>
            ))}
          </div>
        </div>

        <div className="panel lg:col-span-2 overflow-hidden flex flex-col">
          <div className="px-5 py-4 hairline flex items-center justify-between">
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-ink-400">Livrables</div>
              <div className="text-sm text-ink-50 font-medium">{artifacts.length} fichiers generes</div>
            </div>
            <a href={taskZipUrl(id || "")} download className="btn-ghost text-xs">
              <FileDown size={12}/> Telecharger tout (.zip)
            </a>
          </div>
          <div className="grid md:grid-cols-[280px_1fr] min-h-[420px]">
            <div className="border-r border-ink-800 overflow-y-auto max-h-[520px]">
              {artifacts.map((m) => (
                <button
                  key={m.id}
                  onClick={() => preview(m)}
                  className={clsx(
                    "w-full text-left px-4 py-2.5 hover:bg-ink-800/50 transition-colors border-b border-ink-800/70",
                    selected?.id === m.id && "bg-ink-800/60 border-l-2 border-l-gold-400",
                  )}
                >
                  <div className="flex items-center gap-2 text-sm text-ink-100 truncate">
                    <FileCode2 size={13} className="text-gold-300/80 shrink-0" />
                    <span className="truncate font-mono text-[12px]">{m.path}</span>
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-ink-400 mt-1">
                    <span className="uppercase tracking-wider">{m.language}</span>
                    <span>·</span>
                    <span className="tabular-nums">{m.size_bytes} o</span>
                  </div>
                </button>
              ))}
              {artifacts.length === 0 && (
                <div className="p-6 text-center text-sm text-ink-400">Aucun artefact.</div>
              )}
            </div>
            <div className="flex flex-col min-h-0">
              {selected ? (
                <>
                  <div className="px-5 py-3 hairline flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-[11px] text-ink-400 uppercase tracking-wider">{selected.language}</div>
                      <div className="text-sm font-mono truncate">{selected.path}</div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => navigator.clipboard?.writeText(selected.content)}
                        className="btn-ghost text-xs px-2 py-1"
                      >
                        <Copy size={12}/> Copier
                      </button>
                      {id && (
                        <a
                          href={artifactDownloadUrl(id, selected.id)}
                          download
                          className="btn-ghost text-xs px-2 py-1"
                        >
                          <Download size={12}/> Telecharger
                        </a>
                      )}
                    </div>
                  </div>
                  <pre className="flex-1 overflow-auto px-5 py-4 text-[12px] leading-relaxed font-mono text-ink-100 bg-ink-950/60 whitespace-pre max-h-[480px]">
                    {selected.content}
                  </pre>
                </>
              ) : (
                <div className="flex-1 flex items-center justify-center text-sm text-ink-400">
                  Selectionnez un fichier pour l'inspecter.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function deriveVerdict(levels: ValidationLevel[], score: number): "PASS" | "CONDITIONAL_PASS" | "SOFT_FAIL" | "HARD_FAIL" {
  if (!levels.length) return "HARD_FAIL";
  const byLevel = new Map(levels.map((v) => [v.level, v]));
  const l1 = byLevel.get(1); const l2 = byLevel.get(2);
  if (l1 && !l1.passed) return "HARD_FAIL";
  if (l2 && !l2.passed) return "HARD_FAIL";
  const anyFail = levels.some((v) => !v.passed);
  if (anyFail) return score >= 0.7 ? "SOFT_FAIL" : "HARD_FAIL";
  return score >= 0.85 ? "PASS" : "CONDITIONAL_PASS";
}
