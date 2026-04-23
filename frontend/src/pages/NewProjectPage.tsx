import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Send, Wand2, Rocket, ArrowRight } from "lucide-react";
import clsx from "clsx";
import { createTask } from "@/api/tasks";
import { Logo } from "@/components/ui/Logo";

interface Msg {
  role: "assistant" | "user";
  content: string;
}

const INITIAL: Msg[] = [
  {
    role: "assistant",
    content:
      "Bienvenue. Decrivez le projet a generer : domaine, entites, regles metier, conformite. Je clarifierai au besoin, puis le pipeline V1 (5 agents + DAG parallele + validation 5 niveaux) produira un livrable Classe A.",
  },
];

const STARTERS = [
  { title: "API CRUD de base", body: "CRUD API pour une ressource Product avec FastAPI : create, read, list, update, delete. Tests pytest." },
  { title: "Gestion clients VEFA", body: "API de gestion clients pour residences algeriennes : CRUD clients, reservations, paliers VEFA 20/15/35/25/5, TVA 19%, TAP 2%." },
  { title: "Catalogue inventaire", body: "API catalogue produit + stock multi-entrepot : produits, mouvements, seuils, alertes. Reporting agrege." },
  { title: "Ticketing support", body: "Mini SaaS de ticketing : tickets, priorites, SLA, historique evenements, rapports par agent." },
];

export function NewProjectPage() {
  const [messages, setMessages] = useState<Msg[]>(INITIAL);
  const [draft, setDraft] = useState("");
  const [priority, setPriority] = useState<"low" | "medium" | "high" | "critical">("high");
  const [launching, setLaunching] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const nav = useNavigate();

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  function submit() {
    const text = draft.trim();
    if (!text) return;
    setMessages((m) => [
      ...m,
      { role: "user", content: text },
      {
        role: "assistant",
        content: smartAssistantReply(text, messages.length),
      },
    ]);
    setDraft("");
  }

  async function launch() {
    const spec = buildSpec(messages);
    if (!spec) return;
    setLaunching(true);
    try {
      const task = await createTask(spec, priority);
      nav(`/tasks/${task.id}`);
    } catch (e) {
      console.error(e);
      setLaunching(false);
    }
  }

  const canLaunch = messages.some((m) => m.role === "user" && m.content.length >= 20);

  return (
    <div className="px-6 lg:px-10 py-10 max-w-5xl mx-auto">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300/90 mb-1">Orchestration</div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Nouveau projet</h1>
        <p className="text-ink-300 text-sm mt-1">
          Expliquez en francais naturel. Le chat structure la specification, puis l'usine genere le livrable.
        </p>
      </motion.div>

      <div className="mt-8 panel overflow-hidden flex flex-col h-[calc(100vh-260px)] min-h-[520px]">
        <div className="flex-1 overflow-y-auto px-5 py-6 space-y-4">
          <AnimatePresence initial={false}>
            {messages.map((m, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}
                className={clsx("flex gap-3", m.role === "user" ? "justify-end" : "justify-start")}
              >
                {m.role === "assistant" && (
                  <div className="shrink-0 mt-0.5"><Logo size={30} withWordmark={false} /></div>
                )}
                <div
                  className={clsx(
                    "max-w-[78%] px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap",
                    m.role === "user"
                      ? "bg-gradient-to-b from-gold-300/90 to-gold-500/90 text-ink-950 rounded-tr-sm shadow-glow-gold"
                      : "bg-ink-800/70 border border-ink-700/60 text-ink-100 rounded-tl-sm"
                  )}
                >
                  {m.content}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {messages.length === 1 && (
            <div className="mt-6 grid sm:grid-cols-2 gap-3">
              {STARTERS.map((s) => (
                <button
                  key={s.title}
                  onClick={() => setDraft(s.body)}
                  className="panel-inner text-left p-4 hover:border-gold-500/40 transition group"
                >
                  <div className="text-xs uppercase tracking-[0.18em] text-gold-300/80 flex items-center gap-1.5">
                    <Wand2 size={11}/> {s.title}
                  </div>
                  <div className="text-sm text-ink-100 mt-1.5 line-clamp-2">{s.body}</div>
                  <div className="mt-2 text-xs text-ink-400 group-hover:text-gold-300 inline-flex items-center gap-1">
                    Utiliser ce gabarit <ArrowRight size={11}/>
                  </div>
                </button>
              ))}
            </div>
          )}

          <div ref={bottom} />
        </div>

        <div className="border-t border-ink-800 bg-ink-900/60 p-4">
          <div className="flex items-start gap-3">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submit(); }
              }}
              rows={3}
              placeholder="Decrivez entites, endpoints, regles metier, conformite, tests attendus..."
              className="input resize-none font-mono text-[13px] leading-relaxed"
            />
            <div className="flex flex-col gap-2 w-44">
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as "low" | "medium" | "high" | "critical")}
                className="input text-xs"
              >
                <option value="low">Priorite basse</option>
                <option value="medium">Priorite moyenne</option>
                <option value="high">Priorite haute</option>
                <option value="critical">Priorite critique</option>
              </select>
              <button onClick={submit} disabled={!draft.trim()} className="btn-ghost">
                <Send size={13}/> Envoyer
              </button>
            </div>
          </div>
          <div className="mt-3 flex items-center justify-between">
            <div className="text-[11px] text-ink-400">
              <kbd className="px-1 py-0.5 rounded bg-ink-800 border border-ink-700 text-[10px]">Ctrl</kbd>
              {" + "}
              <kbd className="px-1 py-0.5 rounded bg-ink-800 border border-ink-700 text-[10px]">Enter</kbd>
              {" pour envoyer · le bouton a droite lance la generation"}
            </div>
            <button
              onClick={launch}
              disabled={!canLaunch || launching}
              className={clsx("btn-primary", !canLaunch && "opacity-50")}
            >
              {launching ? "Lancement..." : (<><Rocket size={14}/> Lancer la generation</>)}
              {!launching && <Sparkles size={12} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function smartAssistantReply(text: string, turn: number): string {
  if (turn <= 1) {
    return "Parfait. Pour cadrer : quelles entites principales (nom + 2-3 champs cles) ? Y a-t-il des regles metier specifiques (fiscales, temporelles, validations) ? Souhaitez-vous des tests pytest deja dans le livrable ?";
  }
  if (text.length < 40) {
    return "Precisez si possible : endpoints attendus (CRUD complet ? lectures agregees ?), format des identifiants, et eventuelles conformites (RGPD, fiscalite DZ, etc.).";
  }
  return "Tres bien, la specification est exploitable. Vous pouvez affiner si besoin, ou lancer immediatement : le pipeline generera le code, executera ruff + bandit + pytest, puis produira un README et un .zip telechargeable.";
}

function buildSpec(messages: Msg[]): string {
  const userParts = messages.filter((m) => m.role === "user").map((m) => m.content);
  if (userParts.length === 0) return "";
  const spec = userParts.join("\n\n");
  const header = "Generer un projet Python/FastAPI minimal et fonctionnel conforme a la specification suivante.\n\n";
  const footer = "\n\nLivrables attendus : app/main.py, app/models.py, routers, tests/ avec pytest, requirements.txt, Dockerfile, README.md. Code ruff-clean, response_model partout. Reponds UNIQUEMENT avec un JSON {\"files\": {\"<chemin>\": \"<contenu>\"}}.";
  return header + spec + footer;
}
