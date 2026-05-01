/**
 * Espace client — invoices + handoffs.
 */
import { apiClient } from "./client";
import {
  MOCK_HANDOFFS,
  MOCK_INVOICES,
  type ClientHandoff,
  type ClientInvoice,
} from "./client_fixtures";

export type { ClientHandoff, ClientInvoice };

export async function listClientInvoices(): Promise<ClientInvoice[]> {
  try {
    const r = await apiClient.get<ClientInvoice[]>("/client/invoices");
    return r.data;
  } catch {
    return MOCK_INVOICES;
  }
}

export async function listClientHandoffs(): Promise<ClientHandoff[]> {
  try {
    const r = await apiClient.get<ClientHandoff[]>("/client/handoffs");
    return r.data;
  } catch {
    return MOCK_HANDOFFS;
  }
}

export function invoicePdfUrl(token: string): string {
  return `/api/v1/client/invoices/${encodeURIComponent(token)}/pdf`;
}
