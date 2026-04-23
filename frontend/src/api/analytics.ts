import { apiClient } from "./client";

export interface Overview {
  projects: number;
  pass_count: number;
  cpass_count: number;
  fail_count: number;
  pass_rate: number;
  fail_rate: number;
  avg_confidence: number;
  avg_validation: number;
  total_cost_usd: number;
  avg_duration_ms: number;
}

export interface TrendEntry {
  task_id: string;
  verdict: string;
  validation_score: number;
  confidence: number;
  label: string;
  cost_usd: number;
  created_at: string;
  spec_excerpt: string;
  domain_tags: string[];
}

export interface AgentBenchmark {
  agent_id: string;
  agent_name: string;
  executions: number;
  successes: number;
  failures: number;
  success_rate: number;
  avg_duration_ms: number;
  total_cost_usd: number;
  avg_score: number;
  last_update: string | null;
}

export interface ErrorEntry {
  agent_id: string;
  error_type: string;
  sample_message: string;
  occurrences: number;
  first_seen_at: string;
  last_seen_at: string;
}

export interface PendingTask {
  task_id: string;
  prompt_excerpt: string;
  status: string;
  validation_score: number;
  rework_count: number;
  updated_at: string;
}

export interface PromptVariantStat {
  agent_id: string;
  variant_name: string;
  weight: number;
  executions: number;
  wins: number;
  win_rate: number;
  avg_score: number;
  is_active: boolean;
}

export async function getOverview() { const { data } = await apiClient.get<Overview>("/analytics/overview"); return data; }
export async function getTrend(limit = 30) { const { data } = await apiClient.get<TrendEntry[]>(`/analytics/trend?limit=${limit}`); return data; }
export async function getAgents() { const { data } = await apiClient.get<AgentBenchmark[]>("/analytics/agents"); return data; }
export async function getErrors(limit = 10) { const { data } = await apiClient.get<ErrorEntry[]>(`/analytics/errors?limit=${limit}`); return data; }
export async function getPending(limit = 20) { const { data } = await apiClient.get<PendingTask[]>(`/analytics/pending?limit=${limit}`); return data; }
export async function getPromptVariants() { const { data } = await apiClient.get<PromptVariantStat[]>("/analytics/prompt-variants"); return data; }

// V4

export interface Threshold {
  scope: string;
  pass_min: number;
  cpass_min: number;
  soft_fail_min: number;
  sample_count: number;
  last_recomputed_at: string;
}

export interface MarketplaceAgent {
  agent_id: string;
  agent_name: string;
  enabled: boolean;
  status: "healthy" | "at_risk" | "deprecated" | "stub" | "new";
  rank: number | null;
  reason: string;
  executions: number;
  success_rate: number;
  avg_score: number;
  avg_duration_ms: number;
  last_change: string;
}

export interface BacklogItem {
  id: string;
  signature: string;
  category: string;
  priority: "low" | "medium" | "high" | "critical";
  title: string;
  rationale: string;
  evidence: Record<string, unknown>;
  status: string;
  occurrences: number;
  first_seen_at: string;
  last_seen_at: string;
}

export interface PendingQuestion {
  id: string;
  task_id: string;
  question: string;
  category: string;
  evidence: Record<string, unknown>;
  prompt_excerpt: string;
  priority: string;
  created_at: string;
}

export async function getThresholds() { const { data } = await apiClient.get<Threshold[]>("/analytics/thresholds"); return data; }
export async function getMarketplace() { const { data } = await apiClient.get<MarketplaceAgent[]>("/analytics/marketplace"); return data; }
export async function getBacklog(status?: string) {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  const { data } = await apiClient.get<BacklogItem[]>(`/analytics/backlog${q}`);
  return data;
}
export async function getQuestions() { const { data } = await apiClient.get<PendingQuestion[]>("/analytics/questions"); return data; }

export async function answerTaskQuestion(taskId: string, answer: string) {
  const { data } = await apiClient.post(`/tasks/${taskId}/answer`, { answer });
  return data as { ok: boolean; task_id: string };
}
