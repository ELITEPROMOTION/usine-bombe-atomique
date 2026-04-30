/**
 * Espace client — deliverables (livrables telechargeables).
 */
import { apiClient } from "./client";
import {
  MOCK_DELIVERABLES,
  type ClientDeliverable,
} from "./client_fixtures";

export type { ClientDeliverable };

export async function listClientDeliverables(): Promise<ClientDeliverable[]> {
  try {
    const r = await apiClient.get<ClientDeliverable[]>("/client/deliverables");
    return r.data;
  } catch {
    return MOCK_DELIVERABLES;
  }
}

export function buildDownloadUrl(token: string): string {
  // L'URL reelle est servie par le backend ; ici on construit le lien
  // que le frontend ouvrira dans une nouvelle window.
  return `/api/v1/client/deliverables/${encodeURIComponent(token)}/download`;
}
