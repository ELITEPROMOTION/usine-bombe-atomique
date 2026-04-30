/**
 * Espace client — endpoints dashboard.
 *
 * Wiring : tente `/api/v1/client/*` ; si le backend n'est pas pret
 * (404 / network error), retourne les fixtures locales pour permettre
 * le dev offline. Voir ADR-31.
 */
import { apiClient } from "./client";
import {
  MOCK_ACTIVITY,
  MOCK_MILESTONES,
  MOCK_PROJECT,
  type ClientActivity,
  type ClientMilestone,
  type ClientProject,
} from "./client_fixtures";

export type { ClientActivity, ClientMilestone, ClientProject };

async function safeGet<T>(path: string, fallback: T): Promise<T> {
  try {
    const r = await apiClient.get<T>(path);
    return r.data;
  } catch {
    return fallback;
  }
}

export function getClientProject(): Promise<ClientProject> {
  return safeGet<ClientProject>("/client/project", MOCK_PROJECT);
}

export function getClientMilestones(): Promise<ClientMilestone[]> {
  return safeGet<ClientMilestone[]>("/client/milestones", MOCK_MILESTONES);
}

export function getClientActivity(limit = 10): Promise<ClientActivity[]> {
  return safeGet<ClientActivity[]>(
    `/client/activity?limit=${limit}`,
    MOCK_ACTIVITY.slice(0, limit),
  );
}
