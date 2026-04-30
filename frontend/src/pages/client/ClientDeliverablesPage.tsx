import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Package } from "lucide-react";
import {
  buildDownloadUrl,
  listClientDeliverables,
  type ClientDeliverable,
} from "@/api/client_deliverables";
import { DeliverableCard } from "@/design-system";

export function ClientDeliverablesPage() {
  const [items, setItems] = useState<ClientDeliverable[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listClientDeliverables().then((d) => {
      setItems(d);
      setLoading(false);
    });
  }, []);

  return (
    <div className="px-6 lg:px-10 py-10 max-w-5xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300/90 mb-1">
          Livrables
        </div>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-ink-50">
          Vos livrables
        </h1>
        <p className="text-ink-300 text-sm mt-1">
          Tous les fichiers, documents et packages remis tout au long du projet.
        </p>
      </motion.div>

      {loading && (
        <div className="text-ink-400 text-sm">Chargement...</div>
      )}
      {!loading && items.length === 0 && (
        <div className="panel p-12 text-center">
          <Package size={28} className="text-ink-400 mx-auto mb-3" />
          <p className="text-ink-300 text-sm">
            Aucun livrable disponible pour l'instant.
          </p>
          <p className="text-ink-400 text-xs mt-1">
            Vos premieres remises apparaitront ici.
          </p>
        </div>
      )}
      <div className="space-y-3">
        {items.map((d) => (
          <DeliverableCard
            key={d.id}
            deliverable={d}
            downloadUrl={buildDownloadUrl(d.download_token)}
          />
        ))}
      </div>
    </div>
  );
}
