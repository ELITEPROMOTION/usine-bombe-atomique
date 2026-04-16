import { apiClient } from "./client";
import type { Task } from "@/types/task.types";

export async function createTask(prompt: string, priority: Task["priority"] = "high"): Promise<Task> {
  const { data } = await apiClient.post<Task>("/tasks", { prompt, priority });
  return data;
}

export async function getTask(id: string): Promise<Task> {
  const { data } = await apiClient.get<Task>(`/tasks/${id}`);
  return data;
}

export async function listTasks(limit = 50): Promise<Task[]> {
  const { data } = await apiClient.get<Task[]>(`/tasks?limit=${limit}`);
  return data;
}
