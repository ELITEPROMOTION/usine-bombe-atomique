import { useState } from "react";

interface Props {
  onSubmit: (text: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSubmit, disabled }: Props) {
  const [text, setText] = useState("");

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
    setText("");
  };

  return (
    <div style={{ display: "flex", gap: 8, padding: 12, borderTop: "1px solid #374151" }}>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="Decrivez le projet a generer..."
        disabled={disabled}
        rows={3}
        style={{
          flex: 1, padding: 10, borderRadius: 8,
          background: "#111827", color: "#fff",
          border: "1px solid #374151", resize: "vertical",
        }}
      />
      <button
        onClick={submit}
        disabled={disabled || !text.trim()}
        style={{
          padding: "0 20px", borderRadius: 8, border: "none",
          background: "#2563eb", color: "#fff", cursor: "pointer",
          opacity: disabled ? 0.5 : 1,
        }}
      >
        Generer
      </button>
    </div>
  );
}
