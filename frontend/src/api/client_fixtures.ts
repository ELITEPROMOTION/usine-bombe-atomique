/**
 * Mock fixtures pour l'espace client (Phase 9M).
 *
 * Ce fichier est l'unique point de mock data ; les wrappers API
 * `client_*.ts` consomment ces fixtures en fallback quand le backend
 * `/client/*` n'est pas joignable. Voir ADR-31.
 */

export type ClientProjectStatus =
  | "discovery"
  | "qualified"
  | "in_build"
  | "review"
  | "delivered"
  | "completed";

export interface ClientProject {
  project_id: string;
  pack_id: string;
  pack_name: string;
  status: ClientProjectStatus;
  progress_pct: number;            // 0..100
  created_at: string;               // ISO
  estimated_delivery_at: string;    // ISO
  owner_email: string;
  company_name: string;
  next_milestone: string;
  next_milestone_due_at: string;    // ISO
}

export interface ClientMilestone {
  id: string;
  label: string;
  description: string;
  due_at: string;
  status: "pending" | "in_progress" | "done";
}

export interface ClientActivity {
  id: string;
  at: string;
  kind: "build" | "payment" | "deliverable" | "handoff" | "comms";
  title: string;
  detail: string | null;
}

export interface ClientDeliverable {
  id: string;
  name: string;
  category: "code" | "design" | "doc" | "media" | "package";
  size_bytes: number;
  released_at: string;
  download_token: string;
  preview_url: string | null;
}

export interface ClientInvoice {
  invoice_id: string;
  number: string;
  amount_cents: number;
  currency: string;
  status: "draft" | "issued" | "paid" | "refunded";
  issued_at: string;
  paid_at: string | null;
  pdf_token: string;
}

export interface ClientHandoff {
  id: string;
  action_type: "payment_confirm" | "mandate_sign" | "review_approve";
  title: string;
  description: string;
  due_at: string;
  status: "requested" | "notified" | "acknowledged" | "resolved";
  cta_label: string;
  cta_url: string;
}

export interface ClientProfile {
  owner_email: string;
  company_name: string;
  locale: "fr" | "en" | "ar" | "es";
  consent_marketing: boolean;
  consent_analytics: boolean;
  created_at: string;
}


export const MOCK_PROJECT: ClientProject = {
  project_id: "9c1e3b4a-2f7d-4b88-a8b5-23a4d8a1f7e6",
  pack_id: "saas_m",
  pack_name: "SaaS Studio M",
  status: "in_build",
  progress_pct: 64,
  created_at: "2026-04-04T10:21:00Z",
  estimated_delivery_at: "2026-05-12T17:00:00Z",
  owner_email: "client@example.com",
  company_name: "Atelier Lumiere",
  next_milestone: "Revue UI Premium",
  next_milestone_due_at: "2026-05-04T15:00:00Z",
};

export const MOCK_MILESTONES: ClientMilestone[] = [
  {
    id: "m-001",
    label: "Qualification",
    description: "Brief signe + perimetre valide",
    due_at: "2026-04-06T10:00:00Z",
    status: "done",
  },
  {
    id: "m-002",
    label: "Architecture",
    description: "Stack + modeles de donnees + API",
    due_at: "2026-04-12T10:00:00Z",
    status: "done",
  },
  {
    id: "m-003",
    label: "Build interne",
    description: "Generation modules + tests automatises",
    due_at: "2026-04-28T10:00:00Z",
    status: "in_progress",
  },
  {
    id: "m-004",
    label: "Revue UI Premium",
    description: "Walkthrough design system + interactions",
    due_at: "2026-05-04T15:00:00Z",
    status: "pending",
  },
  {
    id: "m-005",
    label: "Livraison",
    description: "Package final + acces deploiement",
    due_at: "2026-05-12T17:00:00Z",
    status: "pending",
  },
];

export const MOCK_ACTIVITY: ClientActivity[] = [
  {
    id: "a-001",
    at: "2026-04-29T09:12:00Z",
    kind: "build",
    title: "Module facturation genere",
    detail: "Stripe + 50 TVA + invoices PDF",
  },
  {
    id: "a-002",
    at: "2026-04-28T14:45:00Z",
    kind: "deliverable",
    title: "Maquettes finalisees",
    detail: "Figma + tokens design",
  },
  {
    id: "a-003",
    at: "2026-04-26T11:30:00Z",
    kind: "payment",
    title: "Acompte 30% confirme",
    detail: null,
  },
  {
    id: "a-004",
    at: "2026-04-24T16:05:00Z",
    kind: "comms",
    title: "Reunion de cadrage",
    detail: "Compte-rendu envoye",
  },
];

export const MOCK_DELIVERABLES: ClientDeliverable[] = [
  {
    id: "d-001",
    name: "Brief signe.pdf",
    category: "doc",
    size_bytes: 482_113,
    released_at: "2026-04-06T10:32:00Z",
    download_token: "tok-brief",
    preview_url: null,
  },
  {
    id: "d-002",
    name: "Architecture & API.pdf",
    category: "doc",
    size_bytes: 1_120_445,
    released_at: "2026-04-12T18:02:00Z",
    download_token: "tok-arch",
    preview_url: null,
  },
  {
    id: "d-003",
    name: "Maquettes finales.fig",
    category: "design",
    size_bytes: 22_405_120,
    released_at: "2026-04-28T14:45:00Z",
    download_token: "tok-fig",
    preview_url: "/preview/d-003",
  },
];

export const MOCK_INVOICES: ClientInvoice[] = [
  {
    invoice_id: "in_001",
    number: "INV-2026-00123",
    amount_cents: 600_000,
    currency: "EUR",
    status: "paid",
    issued_at: "2026-04-04T11:00:00Z",
    paid_at: "2026-04-04T11:14:00Z",
    pdf_token: "pdf-001",
  },
  {
    invoice_id: "in_002",
    number: "INV-2026-00198",
    amount_cents: 700_000,
    currency: "EUR",
    status: "paid",
    issued_at: "2026-04-26T11:30:00Z",
    paid_at: "2026-04-26T11:35:00Z",
    pdf_token: "pdf-002",
  },
  {
    invoice_id: "in_003",
    number: "INV-2026-00251",
    amount_cents: 700_000,
    currency: "EUR",
    status: "issued",
    issued_at: "2026-05-12T17:30:00Z",
    paid_at: null,
    pdf_token: "pdf-003",
  },
];

export const MOCK_HANDOFFS: ClientHandoff[] = [
  {
    id: "h-001",
    action_type: "review_approve",
    title: "Valider la revue UI Premium",
    description:
      "Walkthrough design system + interactions. Approbation requise avant build final.",
    due_at: "2026-05-04T15:00:00Z",
    status: "requested",
    cta_label: "Ouvrir la revue",
    cta_url: "/client/handoffs/h-001",
  },
  {
    id: "h-002",
    action_type: "mandate_sign",
    title: "Signer le mandat de production",
    description: "Mandat eIDAS pour l'execution du build final.",
    due_at: "2026-05-02T12:00:00Z",
    status: "notified",
    cta_label: "Signer",
    cta_url: "/client/handoffs/h-002",
  },
];

export const MOCK_PROFILE: ClientProfile = {
  owner_email: "client@example.com",
  company_name: "Atelier Lumiere",
  locale: "fr",
  consent_marketing: false,
  consent_analytics: true,
  created_at: "2026-04-04T10:21:00Z",
};
