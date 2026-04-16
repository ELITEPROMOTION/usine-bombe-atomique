export type AgentStatus = "pending" | "running" | "success" | "failed" | "timeout" | "skipped";

export interface AgentExecution {
  id: string;
  agent_id: string;
  agent_name: string;
  status: AgentStatus;
  duration_ms: number | null;
  output_json: Record<string, unknown> | null;
  created_at: string;
}
