import { apiClient } from "./client";

export interface InboxItem {
  id: string;
  task_id: string | null;
  tool_id: string | null;
  form_type: "A" | "B" | "C" | null;
  request_kind: string;
  service_name: string | null;
  why: string | null;
  cost_amount: string | null;
  cost_currency: string | null;
  payment_url: string | null;
  free_alternative: boolean | null;
  question_id: string | null;
  suggested_answer: string | null;
  criticality: string;
  fields: Array<{
    id: string;
    label: string;
    type: string;
    required?: boolean;
    mask?: boolean;
    options?: string[];
    placeholder?: string;
    prefilled?: string;
  }>;
  context: string;
  created_at: string;
  expires_at: string;
}

export interface InboxPayload {
  counts: { A: number; B: number; C: number; legacy: number };
  A_accounts: InboxItem[];
  B_payments: InboxItem[];
  C_clarifications: InboxItem[];
  legacy: InboxItem[];
}

export async function getInbox(): Promise<InboxPayload> {
  const { data } = await apiClient.get<InboxPayload>("/inbox");
  return data;
}

export async function submitInboxAnswer(requestId: string, payload: Record<string, unknown>) {
  const { data } = await apiClient.post(
    `/pending-user-inputs/${requestId}/submit`,
    payload,
  );
  return data;
}
