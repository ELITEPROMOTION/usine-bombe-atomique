import { useCallback } from "react";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { ProgressTracker } from "./ProgressTracker";
import { useChatStore } from "@/stores/chatStore";
import { useTaskWebSocket } from "@/hooks/useWebSocket";
import { createTask } from "@/api/tasks";
import type { ChatMessage } from "@/types/chat.types";

export function ChatInterface() {
  const { messages, currentTask, addMessage, setCurrentTask } = useChatStore();
  const { connected } = useTaskWebSocket(currentTask?.id ?? null);

  const handleSubmit = useCallback(async (text: string) => {
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      session_id: currentTask?.session_id ?? "new",
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
      status: "sent",
    };
    addMessage(userMsg);
    try {
      const task = await createTask(text);
      setCurrentTask(task);
      addMessage({
        id: crypto.randomUUID(),
        session_id: task.session_id,
        role: "system",
        content: `Tache ${task.id.slice(0, 8)} creee, statut: ${task.status}`,
        timestamp: new Date().toISOString(),
        status: "sent",
      });
    } catch (err) {
      addMessage({
        id: crypto.randomUUID(),
        session_id: "error",
        role: "system",
        content: `Erreur: ${err instanceof Error ? err.message : "inconnue"}`,
        timestamp: new Date().toISOString(),
        status: "error",
      });
    }
  }, [currentTask, addMessage, setCurrentTask]);

  return (
    <div style={{
      display: "flex", flexDirection: "column",
      height: "100vh", background: "#0f172a", color: "#fff",
    }}>
      <header style={{ padding: 16, borderBottom: "1px solid #374151" }}>
        <h1 style={{ margin: 0, fontSize: 18 }}>
          Usine Bombe Atomique {connected && <span style={{ fontSize: 11, color: "#10b981" }}>- live</span>}
        </h1>
      </header>
      <ProgressTracker task={currentTask} />
      <main style={{ flex: 1, overflowY: "auto", padding: 16 }}>
        {messages.length === 0 && (
          <div style={{ textAlign: "center", color: "#6b7280", marginTop: 64 }}>
            Decrivez votre projet en langage naturel pour lancer la generation.
          </div>
        )}
        {messages.map((m) => <MessageBubble key={m.id} message={m} />)}
      </main>
      <ChatInput onSubmit={handleSubmit} />
    </div>
  );
}
