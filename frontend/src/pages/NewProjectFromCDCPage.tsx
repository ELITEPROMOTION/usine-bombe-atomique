import { useEffect, useMemo, useRef, useState } from "react";
import { Rocket, Download, AlertTriangle, RefreshCw, FileText, Loader2, Sparkles } from "lucide-react";
import clsx from "clsx";
import {
  ProjectStatus,
  SubmitCDCRequest,
  getProjectStatus,
  projectDeliverableUrl,
  submitCDC,
  subscribeProjectUpdates,
} from "@/api/projects";

const SLUG_RE = /^[a-z0-9](?:[a-z0-9-]{0,118}[a-z0-9])?$/;

const STEPS: { key: ProjectStatus; label: string }[] = [
  { key: "intake",       label: "Intake" },
  { key: "clarifying",   label: "Clarification" },
  { key: "decomposing",  label: "Decomposition" },
  { key: "executing",    label: "Execution" },
  { key: "validating",   label: "Validation" },
  { key: "delivered",    label: "Livraison" },
];

interface FormState {
  projectName: string;
  cdcText: string;
  autoResolve: boolean;
}

export function NewProjectFromCDCPage() {
  const [form, setForm] = useState<FormState>({
    projectName: "",
    cdcText: "",
    autoResolve: true,
  });
  const [submitting, setSubmitting] = useState(false);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [status, setStatus] = useState<{
    status: ProjectStatus;
    progress: number;
    current: string;
    completed: number;
    total: number;
    remaining: number;
    error: string | null;
    deliverableUrl: string | null;
  } | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const slugValid = SLUG_RE.test(form.projectName);
  const cdcValid  = form.cdcText.trim().length >= 100 && form.cdcText.length <= 50_000;
  const canSubmit = slugValid && cdcValid && !submitting && !projectId;

  const stepIndex = useMemo(() => {
    if (!status) return -1;
    return STEPS.findIndex((s) => s.key === status.status);
  }, [status]);

  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function startTracking(id: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    const tick = async () => {
      try {
        const s = await getProjectStatus(id);
        setStatus({
          status: s.status,
          progress: s.progress_percent,
          current: s.current_task,
          completed: s.tasks_completed,
          total: s.tasks_total,
          remaining: s.estimated_remaining_minutes,
          error: s.error,
          deliverableUrl: s.deliverable_url,
        });
        if (s.status === "delivered" || s.status === "failed") {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        }
      } catch (err) {
        console.warn("status poll failed", err);
      }
    };
    void tick();
    pollRef.current = setInterval(tick, 5000);

    try {
      const ws = subscribeProjectUpdates(id, (msg) => {
        if (msg.type === "snapshot" || msg.type === "done" || msg.type === "error") {
          void tick();
        }
      });
      wsRef.current = ws;
    } catch (err) {
      console.warn("ws subscribe failed", err);
    }
  }

  async function onSubmit() {
    setWarning(null);
    setSubmitting(true);
    try {
      const payload: SubmitCDCRequest = {
        cdc_text: form.cdcText,
        project_name: form.projectName,
        auto_resolve_ambiguities: form.autoResolve,
        max_duration_minutes: 30,
      };
      const resp = await submitCDC(payload);
      setProjectId(resp.project_id);
      setStatus({
        status: resp.status,
        progress: 0,
        current: "intake",
        completed: 0,
        total: 1,
        remaining: resp.estimated_duration_minutes,
        error: null,
        deliverableUrl: null,
      });
      startTracking(resp.project_id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "submit failed";
      setWarning(msg);
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    if (wsRef.current) wsRef.current.close();
    if (pollRef.current) clearInterval(pollRef.current);
    wsRef.current = null;
    pollRef.current = null;
    setProjectId(null);
    setStatus(null);
    setWarning(null);
  }

  const isTerminal = status?.status === "delivered" || status?.status === "failed";

  return (
    <div className="px-6 lg:px-10 py-10 max-w-5xl mx-auto">
      <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300/90 mb-1">CEO</div>
      <h1 className="font-display text-3xl font-semibold tracking-tight">Nouveau projet UBA</h1>
      <p className="text-ink-300 text-sm mt-2">
        Collez votre cahier des charges. UBA livre la solution complete (code + Docker + tests) en quelques minutes.
      </p>

      {!projectId && (
        <div className="mt-8 panel p-6 space-y-5">
          <div>
            <label className="text-xs uppercase tracking-wider text-ink-300">Nom du projet</label>
            <input
              type="text"
              value={form.projectName}
              onChange={(e) => setForm((f) => ({ ...f, projectName: e.target.value }))}
              placeholder="dendani-residences-v1"
              className="mt-2 w-full px-4 py-3 rounded-lg bg-ink-900/60 border border-ink-700 text-sm text-ink-50 placeholder:text-ink-500 focus:outline-none focus:border-gold-400"
            />
            {form.projectName && !slugValid && (
              <p className="mt-1 text-xs text-amber-400">
                Slug invalide : minuscules, chiffres, tirets uniquement (1-120 chars).
              </p>
            )}
          </div>

          <div>
            <label className="text-xs uppercase tracking-wider text-ink-300">Cahier des charges</label>
            <textarea
              value={form.cdcText}
              onChange={(e) => setForm((f) => ({ ...f, cdcText: e.target.value }))}
              placeholder="Decrivez le projet : objectif, features, stack technique, contraintes metier, livrable attendu..."
              className="mt-2 w-full h-72 px-4 py-3 rounded-lg bg-ink-900/60 border border-ink-700 text-sm text-ink-50 placeholder:text-ink-500 font-mono focus:outline-none focus:border-gold-400"
            />
            <div className="mt-1 flex justify-between text-xs text-ink-400">
              <span>{form.cdcText.length} / 50000 caracteres</span>
              <span>{form.cdcText.length < 100 ? `Minimum 100 chars (${100 - form.cdcText.length} restants)` : "OK"}</span>
            </div>
          </div>

          <label className="flex items-center gap-3 text-sm text-ink-200">
            <input
              type="checkbox"
              checked={form.autoResolve}
              onChange={(e) => setForm((f) => ({ ...f, autoResolve: e.target.checked }))}
              className="w-4 h-4 accent-gold-400"
            />
            Auto-resolution des ambiguites (recommande)
          </label>

          {warning && (
            <div className="flex items-start gap-2 px-3 py-2 rounded bg-red-950/40 border border-red-800 text-sm text-red-200">
              <AlertTriangle size={16} className="mt-0.5" />
              <span>{warning}</span>
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="button"
              onClick={onSubmit}
              disabled={!canSubmit}
              className={clsx(
                "inline-flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium text-sm transition",
                canSubmit
                  ? "bg-gradient-to-br from-gold-400 to-gold-600 text-ink-950 hover:scale-[1.02]"
                  : "bg-ink-800 text-ink-500 cursor-not-allowed",
              )}
            >
              {submitting ? <Loader2 size={16} className="animate-spin" /> : <Rocket size={16} />}
              Lancer le projet
            </button>
          </div>
        </div>
      )}

      {projectId && status && (
        <div className="mt-8 space-y-6">
          <div className="panel p-6">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-[11px] uppercase tracking-wider text-ink-400">Project ID</div>
                <div className="font-mono text-sm text-gold-200 mt-1">{projectId}</div>
              </div>
              <div className="text-right">
                <div className="text-[11px] uppercase tracking-wider text-ink-400">Progression</div>
                <div className="text-2xl font-display text-ink-50 mt-1">{status.progress}%</div>
              </div>
            </div>

            <div className="mt-5 h-2 rounded-full bg-ink-800 overflow-hidden">
              <div
                className={clsx(
                  "h-full transition-all duration-500",
                  status.status === "failed"
                    ? "bg-gradient-to-r from-red-400 to-red-600"
                    : "bg-gradient-to-r from-gold-300 via-gold-400 to-gold-600",
                )}
                style={{ width: `${status.progress}%` }}
              />
            </div>

            <div className="mt-6 grid grid-cols-6 gap-2">
              {STEPS.map((step, idx) => {
                const reached = idx <= stepIndex || status.status === "delivered";
                const active  = idx === stepIndex;
                return (
                  <div
                    key={step.key}
                    className={clsx(
                      "px-2 py-3 rounded-md text-xs text-center transition",
                      active
                        ? "bg-gold-500/20 text-gold-100 border border-gold-500"
                        : reached
                          ? "bg-ink-800 text-ink-100 border border-ink-700"
                          : "bg-ink-900 text-ink-500 border border-ink-800",
                    )}
                  >
                    {step.label}
                  </div>
                );
              })}
            </div>

            <div className="mt-4 grid grid-cols-3 gap-4 text-sm">
              <div>
                <div className="text-[11px] uppercase tracking-wider text-ink-400">Tache courante</div>
                <div className="text-ink-50 mt-1 truncate">{status.current}</div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wider text-ink-400">Avancement</div>
                <div className="text-ink-50 mt-1">{status.completed} / {status.total}</div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wider text-ink-400">Restant estime</div>
                <div className="text-ink-50 mt-1">{status.remaining} min</div>
              </div>
            </div>
          </div>

          {status.status === "delivered" && (
            <div className="panel p-6 border border-emerald-700 bg-emerald-950/20">
              <div className="flex items-center gap-2 text-emerald-300">
                <Sparkles size={18} />
                <span className="font-semibold">Livrable pret</span>
              </div>
              <p className="text-sm text-ink-200 mt-2">
                Telechargez l'archive ZIP. Decompressez puis lancez : <code className="px-1.5 py-0.5 rounded bg-ink-900 text-gold-200">docker compose up -d</code>
              </p>
              <div className="mt-4 flex gap-3">
                <a
                  href={projectDeliverableUrl(projectId)}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium text-sm bg-gradient-to-br from-gold-400 to-gold-600 text-ink-950 hover:scale-[1.02] transition"
                >
                  <Download size={16} />
                  Telecharger le livrable
                </a>
                <button
                  type="button"
                  onClick={reset}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm bg-ink-800 text-ink-100 hover:bg-ink-700"
                >
                  <FileText size={16} />
                  Nouveau projet
                </button>
              </div>
            </div>
          )}

          {status.status === "failed" && (
            <div className="panel p-6 border border-red-700 bg-red-950/20">
              <div className="flex items-center gap-2 text-red-300">
                <AlertTriangle size={18} />
                <span className="font-semibold">Pipeline en erreur</span>
              </div>
              <p className="text-sm text-ink-200 mt-2 font-mono">{status.error || "erreur inconnue"}</p>
              <div className="mt-4 flex gap-3">
                <button
                  type="button"
                  onClick={reset}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm bg-ink-800 text-ink-100 hover:bg-ink-700"
                >
                  <RefreshCw size={16} />
                  Reessayer
                </button>
              </div>
            </div>
          )}

          {!isTerminal && (
            <div className="text-center text-xs text-ink-400">
              <Loader2 size={14} className="inline-block animate-spin mr-2" />
              Pipeline en cours... mises a jour automatiques toutes les 5s
            </div>
          )}
        </div>
      )}
    </div>
  );
}
