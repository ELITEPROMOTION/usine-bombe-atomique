import { create } from "zustand";
import type { ChatMessage } from "@/types/chat.types";
import type { Task } from "@/types/task.types";

interface ChatState {
  messages: ChatMessage[];
  currentTask: Task | null;
  addMessage: (m: ChatMessage) => void;
  setCurrentTask: (t: Task | null) => void;
  reset: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  currentTask: null,
  addMessage: (m) => set((s) => ({ messages: [...s.messages, m] })),
  setCurrentTask: (t) => set({ currentTask: t }),
  reset: () => set({ messages: [], currentTask: null }),
}));
