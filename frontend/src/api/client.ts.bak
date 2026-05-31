import axios from "axios";
import { useAuth } from "@/stores/authStore";

export const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 30_000,
});

apiClient.interceptors.request.use((cfg) => {
  const token = useAuth.getState().token;
  if (token && cfg.headers) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

apiClient.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      useAuth.getState().logout();
      if (location.pathname !== "/login") location.replace("/login");
    }
    return Promise.reject(err);
  },
);
