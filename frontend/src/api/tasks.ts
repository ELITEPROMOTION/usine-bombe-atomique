import { apiClient } from "./client";

export type TaskStatus =
  | "pending" | "analyzing" | "planning" | "distributing"
  | "executing" | "validating" | "reworking"
  | "completed" | "failed" | "cancelled" | "waiting_input";

export interface Task {
  id: string;
  session_id: string;
  user_id: string;
  prompt: string;
  status: TaskStatus;
  priority: string;
  validation_score: number;
  rework_count: number;
  created_at: string;
  updated_at: string;
}

export interface AgentExecution {
  id: string;
  agent_id: string;
  agent_name: string;
  status: string;
  duration_ms: number | null;
  output: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface ValidationLevel {
  level: number;
  name: string;
  score: number;
  passed: boolean;
  details: string | null;
  issues: unknown[];
}

export interface ArtifactMeta {
  id: string;
  filename: string;
  path: string;
  type: string;
  language: string;
  size_bytes: number;
  checksum: string;
}

export interface ArtifactContent extends Omit<ArtifactMeta, "checksum" | "filename"> {
  content: string;
}

export async function createTask(prompt: string, priority: Task["priority"] = "high"): Promise<Task> {
  const { data } = await apiClient.post<Task>("/tasks", { prompt, priority });
  return data;
}

export async function getTask(id: string): Promise<Task> {
  const { data } = await apiClient.get<Task>(`/tasks/${id}`);
  return data;
}

export async function listTasks(limit = 50): Promise<Task[]> {
  const { data } = await apiClient.get<Task[]>(`/tasks?limit=${limit}`);
  return data;
}

export async function listExecutions(taskId: string): Promise<AgentExecution[]> {
  const { data } = await apiClient.get<AgentExecution[]>(`/tasks/${taskId}/executions`);
  return data;
}

export async function getValidation(taskId: string): Promise<ValidationLevel[]> {
  const { data } = await apiClient.get<ValidationLevel[]>(`/tasks/${taskId}/validation`);
  return data;
}

export async function listArtifacts(taskId: string): Promise<ArtifactMeta[]> {
  const { data } = await apiClient.get<ArtifactMeta[]>(`/tasks/${taskId}/artifacts`);
  return data;
}

export async function getArtifact(taskId: string, artifactId: string): Promise<ArtifactContent> {
  const { data } = await apiClient.get<ArtifactContent>(`/tasks/${taskId}/artifacts/${artifactId}`);
  return data;
}

export function artifactDownloadUrl(taskId: string, artifactId: string): string {
  return `/api/v1/tasks/${taskId}/artifacts/${artifactId}/download`;
}

export function taskZipUrl(taskId: string): string {
  return `/api/v1/tasks/${taskId}/download`;
}
