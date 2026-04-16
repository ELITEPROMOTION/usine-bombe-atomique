import type { ChatMessage } from "@/types/chat.types";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div style={{
      display: "flex",
      justifyContent: isUser ? "flex-end" : "flex-start",
      margin: "8px 0",
    }}>
      <div style={{
        maxWidth: "70%",
        padding: "10px 14px",
        borderRadius: 12,
        background: isUser ? "#2563eb" : "#1f2937",
        color: "#fff",
      }}>
        <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 4 }}>
          {message.role} - {new Date(message.timestamp).toLocaleTimeString()}
        </div>
        <div style={{ whiteSpace: "pre-wrap" }}>{message.content}</div>
      </div>
    </div>
  );
}
