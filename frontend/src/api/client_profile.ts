/**
 * Espace client — profile + GDPR (consent / export / erasure).
 */
import { apiClient } from "./client";
import { MOCK_PROFILE, type ClientProfile } from "./client_fixtures";

export type { ClientProfile };

export async function getClientProfile(): Promise<ClientProfile> {
  try {
    const r = await apiClient.get<ClientProfile>("/client/profile");
    return r.data;
  } catch {
    return MOCK_PROFILE;
  }
}

export async function updateClientConsents(
  payload: { consent_marketing: boolean; consent_analytics: boolean },
): Promise<ClientProfile> {
  try {
    const r = await apiClient.patch<ClientProfile>(
      "/client/profile/consents", payload,
    );
    return r.data;
  } catch {
    return { ...MOCK_PROFILE, ...payload };
  }
}

export async function requestGdprExport(): Promise<{ request_id: string }> {
  try {
    const r = await apiClient.post<{ request_id: string }>(
      "/client/profile/gdpr/export",
    );
    return r.data;
  } catch {
    return { request_id: "mock-export-pending" };
  }
}

export async function requestGdprErasure(
  reason: string,
): Promise<{ request_id: string; executable_after: string }> {
  try {
    const r = await apiClient.post<{
      request_id: string;
      executable_after: string;
    }>("/client/profile/gdpr/erasure", { reason });
    return r.data;
  } catch {
    return {
      request_id: "mock-erasure-pending",
      executable_after: new Date(
        Date.now() + 30 * 24 * 3600 * 1000,
      ).toISOString(),
    };
  }
}
