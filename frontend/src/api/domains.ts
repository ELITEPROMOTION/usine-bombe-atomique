import { apiClient as client } from "./client";

export interface DomainInfo {
  domain_id: string;
  latest_version: string;
  description: string;
  all_versions: string[];
  deprecated: string[];
  operations: string[];
}

export interface DomainDetail extends DomainInfo {
  schema: Record<string, unknown>;
  rules_count: number;
  rules: Array<{
    id: string;
    description: string;
    priority: number;
    enabled: boolean;
  }>;
}

export interface ProcessResult {
  success: boolean;
  domain_id: string;
  operation: string;
  output: Record<string, unknown>;
  issues: Array<{ code: string; severity: string; message: string }>;
  correlation_id: string;
  duration_ms: number;
  rules_applied: string[];
}

export async function listDomains(): Promise<{ count: number; domains: DomainInfo[] }> {
  const r = await client.get("/domains/list");
  return r.data;
}

export async function getDomain(id: string): Promise<DomainDetail> {
  const r = await client.get(`/domains/${id}`);
  return r.data;
}

export async function processDomain(
  id: string,
  input: Record<string, unknown>,
  operation = "process",
): Promise<ProcessResult> {
  const r = await client.post(`/domains/${id}/process`, {
    input, operation, permissions: [`${id}:*`],
  });
  return r.data;
}

export interface FeatureFlag {
  flag_name: string;
  description: string | null;
  enabled_globally: boolean;
  rollout_percent: number;
  enabled_tenants_count: number;
  enabled_users_count: number;
}

export async function listFeatures(): Promise<{ count: number; flags: FeatureFlag[] }> {
  const r = await client.get("/features/list");
  return r.data;
}

export async function toggleFeature(name: string, enabled: boolean) {
  const r = await client.post(`/features/${name}/toggle`,
    { enabled, updated_by: "ui" });
  return r.data;
}
