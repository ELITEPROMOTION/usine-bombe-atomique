import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Mail, Building2, Globe, Shield, Download, Trash2, CheckCircle2 } from "lucide-react";
import {
  getClientProfile,
  requestGdprErasure,
  requestGdprExport,
  updateClientConsents,
  type ClientProfile,
} from "@/api/client_profile";

const LOCALE_LABEL: Record<ClientProfile["locale"], string> = {
  fr: "Francais", en: "English", ar: "العربية", es: "Espanol",
};

export function ClientProfilePage() {
  const [profile, setProfile] = useState<ClientProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [exportInfo, setExportInfo] = useState<string | null>(null);
  const [erasureInfo, setErasureInfo] = useState<string | null>(null);
  const [erasureReason, setErasureReason] = useState("");

  useEffect(() => {
    getClientProfile().then((p) => {
      setProfile(p);
      setLoading(false);
    });
  }, []);

  if (loading || !profile) {
    return (
      <div className="px-6 lg:px-10 py-10 max-w-5xl mx-auto text-ink-400 text-sm">
        Chargement...
      </div>
    );
  }

  async function toggleConsent(
    key: "consent_marketing" | "consent_analytics",
    value: boolean,
  ) {
    if (!profile) return;
    const next = await updateClientConsents({
      consent_marketing:
        key === "consent_marketing" ? value : profile.consent_marketing,
      consent_analytics:
        key === "consent_analytics" ? value : profile.consent_analytics,
    });
    setProfile(next);
  }

  async function handleExport() {
    const r = await requestGdprExport();
    setExportInfo(`Demande enregistree (id: ${r.request_id}).`);
  }

  async function handleErasure() {
    if (!erasureReason.trim()) {
      setErasureInfo("Merci de motiver brievement votre demande.");
      return;
    }
    const r = await requestGdprErasure(erasureReason);
    const date = new Date(r.executable_after).toLocaleDateString(
      "fr-FR", { day: "2-digit", month: "long", year: "numeric" },
    );
    setErasureInfo(
      `Demande enregistree (id: ${r.request_id}). Executable a partir du ${date}.`,
    );
    setErasureReason("");
  }

  return (
    <div className="px-6 lg:px-10 py-10 max-w-3xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300/90 mb-1">
          Profil
        </div>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-ink-50">
          Mon compte
        </h1>
        <p className="text-ink-300 text-sm mt-1">
          Coordonnees, preferences de communication, et droits RGPD.
        </p>
      </motion.div>

      <div className="panel p-6 mb-6 space-y-4">
        <ProfileRow icon={<Mail size={14} />} label="Email" value={profile.owner_email} />
        <ProfileRow icon={<Building2 size={14} />} label="Entreprise" value={profile.company_name} />
        <ProfileRow icon={<Globe size={14} />} label="Langue" value={LOCALE_LABEL[profile.locale]} />
        <ProfileRow
          icon={<CheckCircle2 size={14} />}
          label="Client depuis"
          value={new Date(profile.created_at).toLocaleDateString(
            "fr-FR", { day: "2-digit", month: "long", year: "numeric" },
          )}
        />
      </div>

      <div className="panel p-6 mb-6">
        <h2 className="font-medium text-ink-50 tracking-tight mb-4">
          Communications
        </h2>
        <ConsentToggle
          label="Newsletters et offres marketing"
          description="Recevez nos actualites produit et propositions ponctuelles."
          checked={profile.consent_marketing}
          onChange={(v) => toggleConsent("consent_marketing", v)}
        />
        <div className="h-3" />
        <ConsentToggle
          label="Analyses produit"
          description="Permettre la collecte d'evenements anonymises pour ameliorer le produit."
          checked={profile.consent_analytics}
          onChange={(v) => toggleConsent("consent_analytics", v)}
        />
      </div>

      <div className="panel p-6">
        <div className="flex items-center gap-2 mb-2">
          <Shield size={14} className="text-gold-300" />
          <h2 className="font-medium text-ink-50 tracking-tight">
            Vos droits RGPD
          </h2>
        </div>
        <p className="text-xs text-ink-400 mb-5">
          Articles 15 (acces), 17 (oubli), 20 (portabilite). Toute demande
          est tracee et confirmee par email.
        </p>

        <div className="grid sm:grid-cols-2 gap-3">
          <button onClick={handleExport} className="btn-outline">
            <Download size={14} />
            Exporter mes donnees
          </button>
          <button
            onClick={handleErasure}
            className="btn-ghost border border-danger/30 text-danger hover:bg-danger/10"
          >
            <Trash2 size={14} />
            Demander la suppression
          </button>
        </div>

        <div className="mt-4">
          <label
            htmlFor="erasure-reason"
            className="block text-[11px] uppercase tracking-[0.18em] text-ink-400 mb-1"
          >
            Motif (requis pour l'effacement)
          </label>
          <input
            id="erasure-reason"
            value={erasureReason}
            onChange={(e) => setErasureReason(e.target.value)}
            placeholder="ex: fin de contrat, changement de prestataire..."
            className="input"
          />
        </div>

        {exportInfo && (
          <div className="mt-4 text-xs text-success">{exportInfo}</div>
        )}
        {erasureInfo && (
          <div className="mt-2 text-xs text-warn">{erasureInfo}</div>
        )}
      </div>
    </div>
  );
}

function ProfileRow({
  icon, label, value,
}: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-8 h-8 rounded-md bg-ink-800/60 border border-ink-700/60 text-ink-200 flex items-center justify-center">
        {icon}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-[11px] uppercase tracking-[0.18em] text-ink-400">
          {label}
        </div>
        <div className="text-sm text-ink-50 truncate">{value}</div>
      </div>
    </div>
  );
}

interface ToggleProps {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}

function ConsentToggle({ label, description, checked, onChange }: ToggleProps) {
  return (
    <label className="flex items-start gap-4 cursor-pointer select-none group">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`mt-0.5 relative w-10 h-5 rounded-full transition-colors ${
          checked ? "bg-gold-500/70" : "bg-ink-700"
        }`}
      >
        <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-ink-50 transition-transform ${
          checked ? "translate-x-5" : ""
        }`} />
      </button>
      <div className="flex-1 min-w-0">
        <div className="text-sm text-ink-50">{label}</div>
        <div className="text-xs text-ink-400 mt-0.5">{description}</div>
      </div>
    </label>
  );
}
