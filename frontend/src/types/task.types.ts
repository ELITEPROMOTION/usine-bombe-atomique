export type TaskStatus =
  | "pending" | "analyzing" | "planning" | "distributing"
  | "executing" | "validating" | "reworking"
  | "completed" | "failed" | "cancelled";

export interface Task {
  id: string;
  session_id: string;
  user_id: string;
  prompt: string;
  status: TaskStatus;
  priority: "low" | "medium" | "high" | "critical";
  validation_score: number;
  rework_count: number;
  created_at: string;
  updated_at: string;
}
