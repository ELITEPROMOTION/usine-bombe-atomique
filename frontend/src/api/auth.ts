import { apiClient } from "./client";

export async function register(email: string, password: string, fullName: string) {
  const { data } = await apiClient.post("/auth/register", {
    email, password, full_name: fullName,
  });
  return data as { id: string; email: string; full_name: string };
}

export async function login(email: string, password: string) {
  const { data } = await apiClient.post("/auth/login", { email, password });
  return data as { access_token: string; expires_in: number };
}
