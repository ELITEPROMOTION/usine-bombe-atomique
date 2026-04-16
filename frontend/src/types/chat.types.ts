export type MessageRole = "user" | "assistant" | "system";
export type MessageStatus = "sending" | "sent" | "error";
export type SessionStatus = "active" | "completed" | "error" | "archived";

export interface ChatMessage {
  id: string;
  session_id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  status: MessageStatus;
  metadata?: MessageMetadata;
}

export interface MessageMetadata {
  task_id?: string;
  tokens_used?: number;
  processing_time_ms?: number;
  agent_results?: AgentResultSummary[];
  validation_verdict?: "PASS" | "CONDITIONAL_PASS" | "SOFT_FAIL" | "HARD_FAIL";
  validation_score?: number;
  validation_failed_dims?: string[];
}

export interface AgentResultSummary {
  agent_id: string;
  agent_name: string;
  status: "pending" | "running" | "success" | "failed" | "skipped";
  duration_ms: number;
  output_summary: string;
}

export interface ChatSession {
  id: string;
  user_id: string;
  title: string;
  status: SessionStatus;
  message_count: number;
  total_tokens: number;
  created_at: string;
  updated_at: string;
}
