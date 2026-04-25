import { apiClient } from "./client";

export type ProjectStatus =
  | "intake"
  | "clarifying"
  | "decomposing"
  | "executing"
  | "validating"
  | "delivered"
  | "failed";

export interface SubmitCDCRequest {
  cdc_text: string;
  project_name: string;
  tenant_id?: string;
  auto_resolve_ambiguities?: boolean;
  max_duration_minutes?: number;
}

export interface SubmitCDCResponse {
  project_id: string;
  status: ProjectStatus;
  estimated_duration_minutes: number;
}

export interface ProjectStatusPayload {
  project_id: string;
  project_name: string;
  status: ProjectStatus;
  progress_percent: number;
  current_task: string;
  tasks_completed: number;
  tasks_total: number;
  estimated_remaining_minutes: number;
  deliverable_url: string | null;
  error: string | null;
}

export interface ProjectSummary {
  project_id: string;
  project_name: string;
  status: ProjectStatus;
  priority: string;
  created_at: string | null;
  updated_at: string | null;
}

export async function submitCDC(payload: SubmitCDCRequest): Promise<SubmitCDCResponse> {
  const body = {
    cdc_text: payload.cdc_text,
    project_name: payload.project_name,
    tenant_id: payload.tenant_id ?? null,
    auto_resolve_ambiguities: payload.auto_resolve_ambiguities ?? true,
    max_duration_minutes: payload.max_duration_minutes ?? 30,
  };
  const { data } = await apiClient.post<SubmitCDCResponse>("/projects/from_cdc", body);
  return data;
}

export async function getProjectStatus(projectId: string): Promise<ProjectStatusPayload> {
  const { data } = await apiClient.get<ProjectStatusPayload>(`/projects/${projectId}/status`);
  return data;
}

export async function listProjects(limit = 20): Promise<ProjectSummary[]> {
  const { data } = await apiClient.get<ProjectSummary[]>(`/projects?limit=${limit}`);
  return data;
}

export function projectDeliverableUrl(projectId: string): string {
  return `/api/v1/projects/${projectId}/deliverable`;
}

export type ProjectWSMessage =
  | { type: "connected"; task_id: string }
  | { type: "snapshot"; task: { status: string; validation_score: number; rework_count: number; started_at: string | null; completed_at: string | null }; agents: unknown[]; validation: unknown[]; artifacts_count: number }
  | { type: "done"; status: string }
  | { type: "error"; error: string };

export function subscribeProjectUpdates(
  projectId: string,
  onMessage: (msg: ProjectWSMessage) => void,
  onClose?: () => void,
): WebSocket {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws/projects/${projectId}`);
  ws.onmessage = (ev) => {
    try {
      onMessage(JSON.parse(ev.data) as ProjectWSMessage);
    } catch (err) {
      console.error("ws parse failed", err);
    }
  };
  if (onClose) ws.onclose = onClose;
  return ws;
}
