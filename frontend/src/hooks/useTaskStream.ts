import { useEffect, useRef, useState } from "react";

export interface AgentSnap {
  agent_id: string;
  agent_name: string;
  status: string;
  duration_ms: number | null;
}
export interface ValidationSnap {
  level: number;
  name: string;
  score: number;
  passed: boolean;
}
export interface Snapshot {
  task: {
    id: string;
    status: string;
    validation_score: number;
    rework_count: number;
    started_at: string | null;
    completed_at: string | null;
  };
  agents: AgentSnap[];
  validation: ValidationSnap[];
  artifacts_count: number;
}

export function useTaskStream(taskId: string | undefined) {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!taskId) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/tasks/${taskId}`);
    wsRef.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "snapshot") {
          setSnap({
            task: msg.task,
            agents: msg.agents,
            validation: msg.validation,
            artifacts_count: msg.artifacts_count,
          });
        } else if (msg.type === "error") {
          setError(String(msg.error));
        }
      } catch (e) { console.error(e); }
    };
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setError("websocket_error");
    return () => { try { ws.close(); } catch {} };
  }, [taskId]);

  return { snap, connected, error };
}
