import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Mail, Lock, ArrowRight, Shield } from "lucide-react";
import { MarkSVG } from "@/components/ui/Logo";
import { login, register } from "@/api/auth";
import { useAuth } from "@/stores/authStore";

type Mode = "login" | "register";

export function LoginPage() {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const nav = useNavigate();
  const setAuth = useAuth((s) => s.setAuth);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      if (mode === "register") {
        await register(email, password, fullName || email.split("@")[0]);
      }
      const { access_token } = await login(email, password);
      setAuth(access_token, email);
      nav("/", { replace: true });
    } catch (e: unknown) {
      const any_ = e as { response?: { data?: { detail?: string } } };
      setErr(any_?.response?.data?.detail ?? "Authentification echouee");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-6 relative overflow-hidden">
      {/* Full-screen photo backdrop */}
      <div
        className="absolute inset-0 bg-center bg-cover scale-105"
        style={{ backgroundImage: "url(/logo.jpg)" }}
        aria-hidden
      />
      {/* Heavy dark overlay with gold vignette */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(1200px 700px at 50% 40%, rgba(10,10,12,0.55) 0%, rgba(6,6,7,0.88) 55%, rgba(6,6,7,0.97) 100%)",
        }}
        aria-hidden
      />
      <div className="absolute inset-0 pointer-events-none" aria-hidden>
        <div className="absolute -top-40 -left-40 w-[560px] h-[560px] rounded-full bg-gold-500/[0.10] blur-3xl" />
        <div className="absolute -bottom-40 -right-40 w-[560px] h-[560px] rounded-full bg-gold-500/[0.08] blur-3xl" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55, ease: [0.2, 0.8, 0.2, 1] }}
        className="relative w-full max-w-md"
      >
        <div className="flex justify-center mb-8">
          <MarkSVG size={84} />
        </div>

        <div className="text-center mb-8">
          <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300/90 mb-2">
            Groupe Dendani
          </div>
          <h1 className="font-display text-4xl font-semibold text-ink-50 tracking-tight">
            Tech Industrielle
          </h1>
          <div className="mt-3 inline-flex items-center gap-2">
            <span className="h-px w-8 bg-gradient-to-r from-transparent to-gold-400/70" />
            <span className="text-sm uppercase tracking-[0.32em] text-gold-300 font-medium">
              Ahmed DENDANI
            </span>
            <span className="h-px w-8 bg-gradient-to-l from-transparent to-gold-400/70" />
          </div>
          <p className="text-ink-300 text-sm mt-5">
            {mode === "login" ? "Connectez-vous pour orchestrer l'atelier" : "Creez votre compte operateur"}
          </p>
        </div>

        <form onSubmit={onSubmit} className="panel p-6 space-y-4 backdrop-blur-xl">
          {mode === "register" && (
            <div>
              <label className="text-xs uppercase tracking-[0.18em] text-ink-400">Nom complet</label>
              <input
                className="input mt-1.5"
                placeholder="Amine Benali"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
              />
            </div>
          )}
          <div>
            <label className="text-xs uppercase tracking-[0.18em] text-ink-400">Email</label>
            <div className="relative mt-1.5">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" size={15} />
              <input
                type="email"
                className="input pl-9"
                placeholder="operateur@dendani.dz"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
              />
            </div>
          </div>
          <div>
            <label className="text-xs uppercase tracking-[0.18em] text-ink-400">Mot de passe</label>
            <div className="relative mt-1.5">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" size={15} />
              <input
                type="password"
                className="input pl-9"
                placeholder="••••••••"
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
          </div>

          {err && (
            <div className="text-sm text-danger bg-danger/10 border border-danger/30 rounded-lg px-3 py-2">
              {err}
            </div>
          )}

          <button type="submit" disabled={loading} className="btn-primary w-full py-2.5 group">
            {loading ? "Connexion..." : mode === "login" ? "Se connecter" : "Creer le compte"}
            <ArrowRight size={15} className="group-hover:translate-x-0.5 transition-transform" />
          </button>

          <div className="flex items-center justify-between text-xs text-ink-400 pt-1">
            <button
              type="button"
              onClick={() => setMode(mode === "login" ? "register" : "login")}
              className="hover:text-gold-300 transition-colors"
            >
              {mode === "login" ? "Creer un compte" : "J'ai deja un compte"}
            </button>
            <span className="flex items-center gap-1.5">
              <Shield size={11} className="text-gold-500/80" />
              JWT · bcrypt · TLS
            </span>
          </div>
        </form>

        <div className="text-center text-[10px] uppercase tracking-[0.22em] text-ink-400/80 mt-8">
          CDC v3.0 · Ch.11 · IRENE · AUREA · MAGNOLIA · ASTERIA
        </div>
      </motion.div>
    </div>
  );
}
