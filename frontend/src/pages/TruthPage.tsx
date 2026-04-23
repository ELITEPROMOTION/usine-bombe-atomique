import { useEffect, useState } from "react";
import { ShieldCheck, Link2, AlertTriangle } from "lucide-react";
import { Card, CardHeader, Badge, KPIWidget, AlertBanner } from "@/design-system";
import { apiClient } from "@/api/client";

interface VerifyReport {
  events_checked: number;
  broken: Array<{id: number; reason: string}>;
  integrity_ok: boolean;
}

export function TruthPage() {
  const [verify, setVerify] = useState<VerifyReport | null>(null);
  const [stats, setStats] = useState<any>(null);

  async function refresh() {
    try {
      const [v, s] = await Promise.all([
        apiClient.get("/analytics/evidence/verify").catch(() => ({ data: null })),
        apiClient.get("/ctc/stats").catch(() => ({ data: null })),
      ]);
      setVerify(v.data);
      setStats(s.data);
    } catch (e) { console.error(e); }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 30_000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="px-4 lg:px-8 py-6 lg:py-10 max-w-7xl mx-auto">
      <div className="mb-6">
        <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300 mb-1 flex items-center gap-1.5">
          <ShieldCheck size={11} /> V5.3 Truth Engine
        </div>
        <h1 className="font-display text-2xl lg:text-3xl font-semibold">
          Truth Engine Live
        </h1>
        <p className="text-ink-300 text-sm mt-1">
          Chain hash · Triangulation · Phase gates · Evidence ledger
        </p>
      </div>

      {verify && !verify.integrity_ok && (
        <div className="mb-6">
          <AlertBanner
            status="error"
            title={`Integrite chaine compromise : ${verify.broken.length} ruptures`}
          >
            Le chain_hash ne reflecte plus la suite attendue. Investiguer immediatement.
          </AlertBanner>
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <KPIWidget
          icon={<Link2 size={12} />}
          label="Evidence ledger"
          value={verify?.events_checked ?? "—"}
          hint="events verifies"
          status={verify?.integrity_ok ? "success" : "error"}
        />
        <KPIWidget
          icon={<ShieldCheck size={12} />}
          label="Chain integrity"
          value={verify?.integrity_ok ? "OK" : "RUPTURE"}
          status={verify?.integrity_ok ? "success" : "error"}
        />
        <KPIWidget
          icon={<AlertTriangle size={12} />}
          label="Broken links"
          value={verify?.broken.length ?? 0}
          status={(verify?.broken.length ?? 0) === 0 ? "success" : "error"}
        />
        <KPIWidget
          label="Assertions CTC"
          value={stats?.assertions_count ?? "—"}
          hint={stats ? "normalisees" : "en chargement"}
        />
      </div>

      <Card>
        <CardHeader
          icon={<ShieldCheck size={14} />}
          title="Chaine d'evidence"
          hint="SHA-256 hash-linked, append-only, verify_chain toutes les 30 min"
        />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Card variant="outlined" padding="sm">
            <div className="text-xs font-medium text-ink-100 mb-1">1. Record</div>
            <div className="text-[11px] text-ink-400">
              {`SHA-256(payload) + prev_hash -> chain_hash`}
            </div>
            <Badge status="success" size="sm">active</Badge>
          </Card>
          <Card variant="outlined" padding="sm">
            <div className="text-xs font-medium text-ink-100 mb-1">2. Verify</div>
            <div className="text-[11px] text-ink-400">
              Rejoue toute la chaine, detecte toute alteration
            </div>
            <Badge
              status={verify?.integrity_ok ? "success" : "error"}
              size="sm"
            >
              {verify ? (verify.integrity_ok ? "OK" : "failed") : "—"}
            </Badge>
          </Card>
          <Card variant="outlined" padding="sm">
            <div className="text-xs font-medium text-ink-100 mb-1">3. Immutability</div>
            <div className="text-[11px] text-ink-400">
              Triggers PostgreSQL rejettent UPDATE/DELETE
            </div>
            <Badge status="success" size="sm">guaranteed</Badge>
          </Card>
        </div>
      </Card>
    </div>
  );
}
