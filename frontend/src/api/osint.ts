import { apiClient } from "./client";

export type OsintScope = "dendani_only" | "public_sources" | "requires_consent";
export type OsintRisk = "low" | "medium" | "high" | "critical";

export interface OsintModule {
  name: string;
  category: string;
  scope: OsintScope;
  risk: OsintRisk;
}

export interface AuditEvent {
  event_id: string;
  actor: string;
  module: string;
  action: string;
  target: string;
  risk_level: string;
  decision: "allowed" | "denied" | "error";
  consent_id: string | null;
  chain_hash: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface DashboardSummary {
  decisions_7d: { decision: string; count: number }[];
  by_module_7d: { module: string; count: number }[];
  recent_denials: { module: string; target: string; created_at: string }[];
  active_consents: number;
}

export interface ConsentSummary {
  consent_id: string;
  target: string;
  actions: string[];
  contractor: string;
  signed_at: string | null;
  expires_at: string | null;
}

export async function listModules(): Promise<OsintModule[]> {
  const { data } = await apiClient.get<{ modules: OsintModule[] }>("/osint/modules");
  return data.modules;
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  const { data } = await apiClient.get<DashboardSummary>("/osint/dashboard/summary");
  return data;
}

export async function exportAudit(opts: { since?: string; until?: string; limit?: number } = {}): Promise<{
  events: AuditEvent[];
  count: number;
}> {
  const params = new URLSearchParams();
  if (opts.since) params.append("since", opts.since);
  if (opts.until) params.append("until", opts.until);
  if (opts.limit) params.append("limit", String(opts.limit));
  const { data } = await apiClient.get<{ events: AuditEvent[]; count: number }>(
    `/osint/audit/export?${params}`,
  );
  return data;
}

export async function checkAuditIntegrity(): Promise<{
  events_checked: number;
  broken: { id: number; reason: string }[];
  integrity_ok: boolean;
}> {
  const { data } = await apiClient.get("/osint/audit/integrity");
  return data;
}

export async function listConsents(): Promise<{ count: number; consents: ConsentSummary[] }> {
  const { data } = await apiClient.get<{ count: number; consents: ConsentSummary[] }>("/osint/consents");
  return data;
}

export interface AddConsentRequest {
  target: string;
  actions: string[];
  contractor: string;
  contract_pdf_sha256: string;
  expires_at_iso: string;
}

export async function addConsent(payload: AddConsentRequest): Promise<{ consent_id: string }> {
  const { data } = await apiClient.post<{ consent_id: string }>("/osint/consents", payload);
  return data;
}

export async function revokeConsent(consentId: string, reason: string): Promise<{ revoked: boolean }> {
  const { data } = await apiClient.delete<{ revoked: boolean }>(
    `/osint/consents/${consentId}?reason=${encodeURIComponent(reason)}`,
  );
  return data;
}
