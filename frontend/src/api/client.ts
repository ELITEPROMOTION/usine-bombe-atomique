import axios from "axios";

export const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 30_000,
});

apiClient.interceptors.request.use((cfg) => {
  const token = localStorage.getItem("uba_token");
  if (token && cfg.headers) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});
