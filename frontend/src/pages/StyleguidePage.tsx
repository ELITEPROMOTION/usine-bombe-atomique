/**
 * Styleguide page (Phase 9O).
 *
 * Showcase tous les composants du design-system. Route admin
 * `/styleguide` (protegee par AuthGuard).
 */
import { useState } from "react";
import { Inbox, Package, Sparkles, ShieldAlert } from "lucide-react";
import {
  Skeleton, SkeletonText,
  Tabs, TabList, Tab, TabPanel,
  Tooltip, Sheet, EmptyState,
  ProgressGauge,
  ToastProvider, useToast,
} from "@/design-system";

export function StyleguidePage() {
  return (
    <ToastProvider>
      <Inner />
    </ToastProvider>
  );
}

function Inner() {
  const [tab, setTab] = useState("buttons");
  const [sheetOpen, setSheetOpen] = useState(false);
  const toast = useToast();

  return (
    <div className="px-6 lg:px-10 py-10 max-w-6xl mx-auto">
      <div className="mb-8">
        <div className="text-[11px] uppercase tracking-[0.28em] text-gold-300/90 mb-1">
          Phase 9O
        </div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Design System Luxe
        </h1>
        <p className="text-ink-300 text-sm mt-1">
          Tous les composants disponibles dans
          <code className="mx-1 text-gold-300">@/design-system</code>.
        </p>
      </div>

      <Tabs value={tab} onChange={setTab} className="space-y-6">
        <TabList>
          <Tab value="buttons">Buttons & Chips</Tab>
          <Tab value="feedback">Feedback</Tab>
          <Tab value="overlays">Overlays</Tab>
          <Tab value="data">Data display</Tab>
        </TabList>

        <TabPanel value="buttons">
          <Section title="Boutons">
            <div className="flex flex-wrap gap-3">
              <button className="btn-primary"><Sparkles size={14} /> Action primaire</button>
              <button className="btn-outline">Outline</button>
              <button className="btn-ghost">Ghost</button>
              <button className="btn-primary" disabled>Disabled</button>
            </div>
          </Section>
          <Section title="Chips">
            <div className="flex flex-wrap gap-2">
              <span className="chip-gold">Gold</span>
              <span className="chip-success">Success</span>
              <span className="chip-warn">Warn</span>
              <span className="chip-danger">Danger</span>
              <span className="chip-neutral">Neutral</span>
            </div>
          </Section>
        </TabPanel>

        <TabPanel value="feedback">
          <Section title="Skeleton">
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="panel p-5">
                <SkeletonText lines={4} />
              </div>
              <div className="panel p-5 flex items-center gap-3">
                <Skeleton width="2.75rem" height="2.75rem" rounded="full" />
                <div className="flex-1 space-y-2">
                  <Skeleton height="0.875rem" width="60%" />
                  <Skeleton height="0.7rem" width="80%" />
                </div>
              </div>
            </div>
          </Section>
          <Section title="Toasts">
            <div className="flex flex-wrap gap-2">
              <button className="btn-outline" onClick={() => toast.push({
                tone: "success", title: "Sauvegarde",
                description: "Vos modifications ont ete enregistrees.",
              })}>Success</button>
              <button className="btn-outline" onClick={() => toast.push({
                tone: "warn", title: "Attention",
                description: "Un parametre est proche de la limite.",
              })}>Warn</button>
              <button className="btn-outline" onClick={() => toast.push({
                tone: "danger", title: "Erreur",
                description: "Le webhook n'a pas pu etre traite.",
              })}>Danger</button>
              <button className="btn-outline" onClick={() => toast.push({
                tone: "info", title: "Info",
              })}>Info</button>
            </div>
          </Section>
        </TabPanel>

        <TabPanel value="overlays">
          <Section title="Tooltip">
            <div className="flex gap-6">
              {(["top", "bottom", "left", "right"] as const).map((side) => (
                <Tooltip key={side} side={side} content={`Tooltip ${side}`}>
                  <button className="btn-outline">{side}</button>
                </Tooltip>
              ))}
            </div>
          </Section>
          <Section title="Sheet (drawer)">
            <button className="btn-primary" onClick={() => setSheetOpen(true)}>
              Ouvrir le drawer
            </button>
            <Sheet
              open={sheetOpen}
              onClose={() => setSheetOpen(false)}
              title="Reglages"
              description="Modifier les preferences de notification."
            >
              <div className="space-y-3">
                <p className="text-sm text-ink-200">
                  Le contenu du drawer va ici. Click outside, ESC ou
                  bouton X pour fermer.
                </p>
                <button className="btn-outline" onClick={() => setSheetOpen(false)}>
                  Annuler
                </button>
              </div>
            </Sheet>
          </Section>
        </TabPanel>

        <TabPanel value="data">
          <Section title="ProgressGauge">
            <div className="flex flex-wrap gap-8 items-center">
              <ProgressGauge value={32} sublabel="Discover" size="sm" />
              <ProgressGauge value={64} sublabel="Build"    size="md" />
              <ProgressGauge value={92} sublabel="Delivery" size="lg" />
            </div>
          </Section>
          <Section title="EmptyState">
            <EmptyState
              icon={Inbox}
              title="Aucune notification"
              description="Vous serez prevenu des qu'une action sera requise."
              action={<button className="btn-primary">
                <Sparkles size={14} /> Commencer
              </button>}
            />
          </Section>
          <Section title="EmptyState (alt)">
            <div className="grid sm:grid-cols-2 gap-4">
              <EmptyState
                icon={Package} title="Aucun livrable"
                description="Vos premieres remises apparaitront ici."
              />
              <EmptyState
                icon={ShieldAlert} title="Pas d'alerte"
                description="Tous les SLO sont dans les budgets d'erreur."
              />
            </div>
          </Section>
        </TabPanel>
      </Tabs>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="panel p-6">
      <h2 className="text-[11px] uppercase tracking-[0.22em] text-gold-300/90 mb-4">
        {title}
      </h2>
      {children}
    </section>
  );
}
