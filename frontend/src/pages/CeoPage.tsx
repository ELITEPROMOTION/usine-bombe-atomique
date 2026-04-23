import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  TrendingUp, DollarSign, Gauge, Activity, AlertTriangle,
  Crown, Brain, FlaskConical, Target, ChevronRight, Sparkles,
  Store, HelpCircle, ListChecks, SlidersHorizontal, CheckCircle2, Send,
} from "lucide-react";
import clsx from "clsx";
import {
  getOverview, getTrend, getAgents, getErrors, getPending, getPromptVariants,
  getThresholds, getMarketplace, getBacklog, getQuestions, answerTaskQuestion,
  type Overview, type TrendEntry, type AgentBenchmark, type ErrorEntry,
  type PendingTask, type PromptVariantStat,
  type Threshold, type MarketplaceAgent, type BacklogItem, type PendingQuestion,
} from "@/api/analytics";
import { StatusChip } from "@/components/ui/StatusChip";

export function CeoPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [trend, setTrend] = useState<TrendEntry[]>([]);
  const [agents, setAgents] = useState<AgentBenchmark[]>([]);
  const [errors, setErrors] = useState<ErrorEntry[]>([]);
  const [pending, setPending] = useState<PendingTask[]>([]);
  const [variants, setVariants] = useState<PromptVariantStat[]>([]);
  const [thresholds, setThresholds] = useState<Threshold[]>([]);
  const [market, setMarket] = useState<MarketplaceAgent[]>([]);
  const [backlog, setBacklog] = useState<BacklogItem[]>([]);
  const [questions, setQuestions] = useState<PendingQuestion[]>([]);

  async function refreshAll() {
    const [o, t, a, e, p, v, th, mk, bl, qs] = await Promise.all([
      getOverview(), getTrend(30), getAgents(), getErrors(10), getPending(20),
      getPromptVariants(), getThresholds(), getMarketplace(), getBacklog("open"),
      getQuestions(),
    ]);
    setOverview(o); setTrend(t); setAgents(a); setErrors(e); setPending(p);
    setVariants(v); setThresholds(th); setMarket(mk); setBacklog(bl); setQuestions(qs);
  }

  useEffect(() => { refreshAll(); }, []);

  const roiBase = Math.max(1, overview?.projects ?? 0);
  const quality = (overview?.avg_confidence ?? 0) * 100;

  return (
    <div className="px-6 lg:px-10 py-10 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        className="flex items-end justify-between mb-8 flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.28em] text-gold-300/90 mb-1">
            <Crown size={11} /> Executive
          </div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Dashboard CEO</h1>
          <p className="text-ink-300 text-sm mt-1">
            Memoire V3 · Couts Anthropic · Qualite composite · Decisions en attente
          </p>
        </div>
        <Link to="/new" className="btn-primary"><Sparkles size={15} /> Nouveau projet</Link>
      </motion.div>

      <div className="grid md:grid-cols-4 gap-4 mb-8">
        <Kpi icon={<Activity size={15}/>}   label="Projets indexes"   value={overview?.projects ?? 0}
             trend={`${overview?.pass_count ?? 0} PASS`} />
        <Kpi icon={<Gauge size={15}/>}       label="Qualite moyenne"   value={`${quality.toFixed(1)}%`}
             trend={`label : ${labelFor(overview?.avg_confidence ?? 0)}`} accent={quality >= 85 ? "gold" : "neutral"} />
        <Kpi icon={<DollarSign size={15}/>}  label="Cout cumule"       value={`$${(overview?.total_cost_usd ?? 0).toFixed(3)}`}
             trend={`~$${((overview?.total_cost_usd ?? 0) / roiBase).toFixed(4)} / projet`} />
        <Kpi icon={<TrendingUp size={15}/>}  label="Taux PASS"         value={`${((overview?.pass_rate ?? 0) * 100).toFixed(0)}%`}
             trend={`${overview?.fail_count ?? 0} echecs`} accent={(overview?.pass_rate ?? 0) >= 0.85 ? "gold" : "neutral"} />
      </div>

      <div className="grid lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3 panel p-5">
          <Header icon={<TrendingUp size={14}/>} title="Qualite des 30 derniers projets" hint="Confidence composite (0-100%)"/>
          <TrendChart data={trend.slice().reverse()} />
          <div className="mt-5 divide-y divide-ink-800/70">
            {trend.slice(0, 8).map((t) => (
              <Link key={t.task_id} to={`/tasks/${t.task_id}/results`}
                className="py-2.5 flex items-center gap-3 hover:bg-ink-800/40 px-2 rounded-md transition">
                <VerdictDot verdict={t.verdict} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-ink-100 truncate">{t.spec_excerpt || "(sans spec)"}</div>
                  <div className="text-[10.5px] text-ink-400 mt-0.5 flex gap-1.5 items-center">
                    {t.domain_tags.slice(0, 3).map((d) => (
                      <span key={d} className="chip-neutral px-1.5 py-0 text-[9px]">{d}</span>
                    ))}
                    <span>{new Date(t.created_at).toLocaleString("fr-FR")}</span>
                  </div>
                </div>
                <div className="text-right tabular-nums">
                  <div className="text-sm text-ink-100">{(t.confidence * 100).toFixed(1)}%</div>
                  <div className="text-[10px] text-ink-400">${t.cost_usd.toFixed(4)}</div>
                </div>
                <ChevronRight size={13} className="text-ink-500"/>
              </Link>
            ))}
            {trend.length === 0 && <div className="text-sm text-ink-400 p-4 text-center">Aucun projet indexe.</div>}
          </div>
        </div>

        <div className="lg:col-span-2 space-y-6">
          <div className="panel p-5">
            <Header icon={<AlertTriangle size={14}/>} title="Decisions en attente"
                    hint="SOFT_FAIL / retravaillees / scores faibles"/>
            <div className="mt-3 space-y-2 max-h-[320px] overflow-y-auto pr-1">
              {pending.map((p) => (
                <Link key={p.task_id} to={`/tasks/${p.task_id}/results`}
                      className="panel-inner p-3 block hover:border-gold-500/40 transition">
                  <div className="flex items-center gap-2 mb-1">
                    <StatusChip status={p.status}/>
                    <span className="text-[11px] text-ink-400 tabular-nums ml-auto">
                      {(p.validation_score * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="text-[13px] text-ink-100 line-clamp-2">{p.prompt_excerpt}</div>
                </Link>
              ))}
              {pending.length === 0 && <div className="text-sm text-ink-400 py-4 text-center">Rien en attente.</div>}
            </div>
          </div>

          <div className="panel p-5">
            <Header icon={<Brain size={14}/>} title="Top agents" hint="Classement par score moyen"/>
            <div className="mt-3 space-y-2">
              {agents.slice(0, 6).sort((a,b) => b.avg_score - a.avg_score).map((a) => (
                <div key={a.agent_id} className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-ink-100 truncate">{a.agent_name}</div>
                    <div className="text-[10.5px] text-ink-400 font-mono truncate">{a.agent_id}</div>
                  </div>
                  <div className="w-24 h-1.5 bg-ink-800 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-gold-300 to-gold-500"
                         style={{ width: `${Math.max(0, Math.min(1, a.avg_score)) * 100}%` }}/>
                  </div>
                  <div className="text-xs tabular-nums text-ink-100 w-14 text-right">{(a.avg_score * 100).toFixed(1)}%</div>
                </div>
              ))}
              {agents.length === 0 && <div className="text-sm text-ink-400 py-2 text-center">Pas encore de runs.</div>}
            </div>
          </div>
        </div>

        <div className="lg:col-span-3 panel p-5">
          <Header icon={<Target size={14}/>} title="Performances agents (execution volume)"
                  hint="Executions cumulees par agent depuis l'origine"/>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[10px] uppercase tracking-[0.16em] text-ink-400">
                <tr><th className="text-left pb-2 pl-1">Agent</th>
                    <th className="text-right">Exec</th>
                    <th className="text-right">Taux</th>
                    <th className="text-right">Duree moy</th>
                    <th className="text-right pr-1">Score</th></tr>
              </thead>
              <tbody className="divide-y divide-ink-800/70">
                {agents.map((a) => (
                  <tr key={a.agent_id}>
                    <td className="py-2 pl-1">
                      <div className="text-ink-100">{a.agent_name}</div>
                      <div className="text-[10.5px] font-mono text-ink-400">{a.agent_id}</div>
                    </td>
                    <td className="text-right tabular-nums">{a.executions}</td>
                    <td className={clsx("text-right tabular-nums",
                      a.success_rate >= 0.95 ? "text-success" : a.success_rate >= 0.8 ? "text-ink-100" : "text-danger")}>
                      {(a.success_rate * 100).toFixed(0)}%
                    </td>
                    <td className="text-right tabular-nums">{(a.avg_duration_ms / 1000).toFixed(1)}s</td>
                    <td className="text-right tabular-nums pr-1">{(a.avg_score * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="lg:col-span-2 panel p-5">
          <Header icon={<AlertTriangle size={14}/>} title="Catalogue d'erreurs" hint="Top frequences, toutes iterations"/>
          <div className="mt-3 space-y-2 max-h-[260px] overflow-y-auto pr-1">
            {errors.map((e, i) => (
              <div key={i} className="panel-inner p-3">
                <div className="flex items-center gap-2 justify-between">
                  <span className="chip-danger">{e.error_type}</span>
                  <span className="text-xs text-ink-400 tabular-nums">x{e.occurrences}</span>
                </div>
                <div className="text-[11.5px] text-ink-200 mt-1 font-mono truncate">{e.agent_id}</div>
                <div className="text-[11px] text-ink-400 mt-1 line-clamp-2">{e.sample_message}</div>
              </div>
            ))}
            {errors.length === 0 && <div className="text-sm text-ink-400 py-2 text-center">Zero erreur catalogued. Beau travail.</div>}
          </div>
        </div>

        {/* V4 · Questions d'escalade */}
        {questions.length > 0 && (
          <div className="lg:col-span-5 panel p-5 ring-1 ring-gold-500/30">
            <Header icon={<HelpCircle size={14}/>} title="Escalade : questions en attente"
                    hint="UNE question precise generee par le systeme"/>
            <div className="mt-4 space-y-3">
              {questions.map((q) => (
                <QuestionCard key={q.id} q={q} onResolved={refreshAll} />
              ))}
            </div>
          </div>
        )}

        {/* V4 · Thresholds auto-tunes */}
        <div className="lg:col-span-2 panel p-5">
          <Header icon={<SlidersHorizontal size={14}/>} title="Seuils auto-tunes"
                  hint="Calibrage dynamique des verdicts"/>
          <div className="mt-3 space-y-3">
            {thresholds.length === 0 && <div className="text-sm text-ink-400">Pas encore de tuning.</div>}
            {thresholds.map((t) => (
              <div key={t.scope} className="panel-inner p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="chip-gold">{t.scope}</span>
                  <span className="text-[10.5px] text-ink-400">{t.sample_count} ech.</span>
                </div>
                <ThresholdBar label="PASS"  value={t.pass_min}  />
                <ThresholdBar label="CPASS" value={t.cpass_min} />
                <ThresholdBar label="SOFT"  value={t.soft_fail_min} />
                <div className="text-[10px] text-ink-500 mt-1">
                  recalcul : {new Date(t.last_recomputed_at).toLocaleString("fr-FR")}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* V4 · Marketplace */}
        <div className="lg:col-span-3 panel p-5">
          <Header icon={<Store size={14}/>} title="Marketplace des agents"
                  hint="Benchmark continu & statut dynamique"/>
          <div className="mt-3 divide-y divide-ink-800/70">
            {market.map((m) => (
              <div key={m.agent_id} className="py-2.5 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-ink-100 truncate flex items-center gap-2">
                    {m.agent_name}
                    {!m.enabled && <span className="chip-danger px-1.5 py-0 text-[9px]">off</span>}
                  </div>
                  <div className="text-[10.5px] text-ink-400 truncate">{m.reason}</div>
                </div>
                <div className="text-right tabular-nums text-xs text-ink-300">
                  <div>{m.executions} exec</div>
                  <div className="text-[10px] text-ink-500">{(m.success_rate*100).toFixed(0)}% ok</div>
                </div>
                <MarketStatus status={m.status} />
              </div>
            ))}
            {market.length === 0 && <div className="text-sm text-ink-400 py-2 text-center">Aucun snapshot.</div>}
          </div>
        </div>

        {/* V4 · Backlog auto-ameliorations */}
        <div className="lg:col-span-5 panel p-5">
          <Header icon={<ListChecks size={14}/>} title="Backlog auto-ameliorations"
                  hint="Propositions generees depuis les incidents reels"/>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[10px] uppercase tracking-[0.16em] text-ink-400">
                <tr>
                  <th className="text-left pb-2 pl-1">Priorite</th>
                  <th className="text-left">Categorie</th>
                  <th className="text-left">Titre</th>
                  <th className="text-right">Occurrences</th>
                  <th className="text-right pr-1">Derniere</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800/70">
                {backlog.map((b) => (
                  <tr key={b.id} className="align-top">
                    <td className="py-2 pl-1"><PriorityPill priority={b.priority} /></td>
                    <td className="py-2"><span className="chip-neutral">{b.category}</span></td>
                    <td className="py-2">
                      <div className="text-ink-100">{b.title}</div>
                      <div className="text-[10.5px] text-ink-400 mt-0.5 line-clamp-2">{b.rationale}</div>
                    </td>
                    <td className="text-right tabular-nums">{b.occurrences}</td>
                    <td className="text-right pr-1 text-[10.5px] text-ink-400">
                      {new Date(b.last_seen_at).toLocaleDateString("fr-FR")}
                    </td>
                  </tr>
                ))}
                {backlog.length === 0 && (
                  <tr><td colSpan={5} className="py-4 text-center text-sm text-ink-400">
                    Zero proposition. Le systeme est en bonne sante.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="lg:col-span-5 panel p-5">
          <Header icon={<FlaskConical size={14}/>} title="A/B testing des prompts"
                  hint="Variantes actives, score moyen, taux de victoire"/>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[10px] uppercase tracking-[0.16em] text-ink-400">
                <tr>
                  <th className="text-left pb-2 pl-1">Agent</th>
                  <th className="text-left">Variante</th>
                  <th className="text-right">Weight</th>
                  <th className="text-right">Exec</th>
                  <th className="text-right">Wins</th>
                  <th className="text-right">Win rate</th>
                  <th className="text-right pr-1">Score moyen</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800/70">
                {variants.map((v, i) => (
                  <tr key={i}>
                    <td className="py-2 pl-1 font-mono text-[12px] text-ink-300">{v.agent_id}</td>
                    <td className="text-ink-100">{v.variant_name}</td>
                    <td className="text-right tabular-nums">{v.weight.toFixed(2)}</td>
                    <td className="text-right tabular-nums">{v.executions}</td>
                    <td className="text-right tabular-nums">{v.wins}</td>
                    <td className="text-right tabular-nums">{(v.win_rate * 100).toFixed(0)}%</td>
                    <td className="text-right tabular-nums pr-1">{(v.avg_score * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function Kpi({ icon, label, value, trend, accent }: {
  icon: React.ReactNode; label: string; value: number | string; trend: string;
  accent?: "gold" | "neutral";
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      className={clsx("panel p-5", accent === "gold" && "ring-1 ring-gold-500/20")}>
      <div className="flex items-center gap-2 text-ink-300 text-xs uppercase tracking-[0.18em]">
        <span className={accent === "gold" ? "text-gold-300" : "text-ink-400"}>{icon}</span> {label}
      </div>
      <div className="mt-3 text-3xl font-semibold tracking-tight text-ink-50 tabular-nums">{value}</div>
      <div className="text-xs text-ink-400 mt-1">{trend}</div>
    </motion.div>
  );
}

function Header({ icon, title, hint }: { icon: React.ReactNode; title: string; hint: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.18em] text-ink-400 flex items-center gap-1.5">
        <span className="text-gold-300/80">{icon}</span> {title}
      </div>
      <div className="text-sm text-ink-100 font-medium mt-0.5">{hint}</div>
    </div>
  );
}

function VerdictDot({ verdict }: { verdict: string }) {
  const color = verdict === "PASS" ? "bg-success"
              : verdict === "CONDITIONAL_PASS" ? "bg-warn"
              : verdict === "SOFT_FAIL" ? "bg-warn"
              : "bg-danger";
  return <span className={clsx("w-2 h-2 rounded-full", color)} />;
}

function TrendChart({ data }: { data: TrendEntry[] }) {
  if (data.length === 0) {
    return <div className="h-36 flex items-center justify-center text-sm text-ink-400">Pas de donnee</div>;
  }
  const max = 1.0;
  return (
    <div className="mt-4 flex items-end gap-1 h-36">
      {data.map((d, i) => {
        const h = Math.max(2, (d.confidence / max) * 100);
        const color = d.verdict === "PASS" ? "from-gold-300 to-gold-500"
                    : d.verdict === "CONDITIONAL_PASS" ? "from-warn/60 to-warn"
                    : "from-danger/40 to-danger";
        return (
          <div key={i} className="flex-1 group relative">
            <div className={clsx("w-full rounded-t-md bg-gradient-to-t", color)} style={{ height: `${h}%` }}/>
            <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 pointer-events-none z-10
                            bg-ink-900 border border-ink-700 rounded-md px-2 py-1 text-[10.5px] whitespace-nowrap shadow-panel">
              {(d.confidence * 100).toFixed(1)}% · {d.verdict}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function labelFor(score: number): string {
  if (score >= 0.90) return "very_high";
  if (score >= 0.75) return "high";
  if (score >= 0.55) return "medium";
  if (score >= 0.30) return "low";
  return "very_low";
}

function ThresholdBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-2 text-[11px] mb-1">
      <span className="w-12 text-ink-400 uppercase tracking-[0.12em]">{label}</span>
      <div className="flex-1 h-1.5 bg-ink-800 rounded-full overflow-hidden">
        <div className="h-full bg-gradient-to-r from-gold-300 to-gold-500"
             style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
      </div>
      <span className="w-12 text-right tabular-nums text-ink-100">{(value * 100).toFixed(1)}</span>
    </div>
  );
}

function MarketStatus({ status }: { status: string }) {
  const cls =
    status === "healthy" ? "chip-success" :
    status === "at_risk" ? "chip-warn" :
    status === "deprecated" ? "chip-danger" :
    status === "stub" ? "chip-neutral" : "chip-gold";
  return <span className={cls}>{status}</span>;
}

function PriorityPill({ priority }: { priority: string }) {
  const cls =
    priority === "critical" ? "chip-danger" :
    priority === "high" ? "chip-warn" :
    priority === "medium" ? "chip-gold" : "chip-neutral";
  return <span className={cls}>{priority}</span>;
}

function QuestionCard({ q, onResolved }: { q: PendingQuestion; onResolved: () => void }) {
  const [answer, setAnswer] = useState("");
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);

  async function send() {
    if (!answer.trim()) return;
    setSending(true);
    try {
      await answerTaskQuestion(q.task_id, answer);
      setDone(true);
      setAnswer("");
      setTimeout(onResolved, 400);
    } finally { setSending(false); }
  }

  return (
    <div className="panel-inner p-4 relative overflow-hidden">
      <div className="flex items-center gap-2 mb-2">
        <span className="chip-gold"><HelpCircle size={11}/> {q.category}</span>
        <span className="text-[10.5px] text-ink-400 font-mono">{q.task_id.slice(0, 8)}</span>
        <span className="chip-neutral">{q.priority}</span>
        <span className="text-[10.5px] text-ink-500 ml-auto">
          {new Date(q.created_at).toLocaleTimeString("fr-FR")}
        </span>
      </div>
      <div className="text-[13px] text-ink-300 italic line-clamp-1 mb-2">{q.prompt_excerpt}...</div>
      <div className="text-sm text-ink-50 leading-relaxed mb-3">{q.question}</div>
      {done ? (
        <div className="text-success text-sm flex items-center gap-2">
          <CheckCircle2 size={14}/> Reponse envoyee. La tache est re-enqueuee.
        </div>
      ) : (
        <div className="flex gap-2 items-start">
          <textarea
            className="input flex-1 font-mono text-[12px] resize-none"
            rows={2}
            placeholder="Votre reponse..."
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
          />
          <button onClick={send} disabled={!answer.trim() || sending} className="btn-primary">
            <Send size={13}/> {sending ? "..." : "Repondre"}
          </button>
        </div>
      )}
    </div>
  );
}
