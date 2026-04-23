import { apiClient as client } from "./client";

export interface WorkflowSchedule {
  task_name: string;
  cron_expression: string;
  tier: number;
  enabled: boolean;
  paused_at: string | null;
  last_run: string | null;
  next_run: string | null;
  description: string;
}

export interface WorkflowRun {
  run_id: string;
  task_name: string;
  worker_name?: string;
  status: "running" | "succeeded" | "failed" | "timeout" | "dead_letter";
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  tries: number;
  trigger_kind: "cron" | "event" | "manual";
  error: string | null;
}

export interface WorkflowMetrics {
  days: number;
  total_runs: number;
  total_success: number;
  total_failure: number;
  global_success_rate: number;
  per_task: Array<{
    task_name: string;
    success_count: number;
    failure_count: number;
    avg_duration_ms: number;
    p99_duration_ms: number;
    last_run: string | null;
    success_rate: number;
  }>;
}

export async function getScheduled(): Promise<{ count: number; schedules: WorkflowSchedule[] }> {
  const r = await client.get("/workflows/scheduled");
  return r.data;
}

export async function getHistory(limit = 100, taskName?: string): Promise<{ count: number; runs: WorkflowRun[] }> {
  const q = new URLSearchParams({ limit: String(limit) });
  if (taskName) q.set("task_name", taskName);
  const r = await client.get(`/workflows/history?${q}`);
  return r.data;
}

export async function getMetrics(days = 7): Promise<WorkflowMetrics> {
  const r = await client.get(`/workflows/metrics?days=${days}`);
  return r.data;
}

export async function getActive(): Promise<{ count: number; runs: WorkflowRun[] }> {
  const r = await client.get("/workflows/active");
  return r.data;
}

export async function getFailures(limit = 50) {
  const r = await client.get(`/workflows/failures?limit=${limit}`);
  return r.data;
}

export async function getDependencies() {
  const r = await client.get("/workflows/dependencies");
  return r.data;
}

export async function triggerTask(name: string, payload: Record<string, unknown> = {}) {
  const r = await client.post(`/workflows/trigger/${name}`, payload);
  return r.data;
}

export async function pauseTask(name: string) {
  const r = await client.post(`/workflows/pause/${name}`);
  return r.data;
}

export async function resumeTask(name: string) {
  const r = await client.post(`/workflows/resume/${name}`);
  return r.data;
}
