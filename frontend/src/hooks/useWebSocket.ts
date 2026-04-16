import { useEffect, useRef, useState } from "react";

export interface WsEvent {
  type: string;
  task_id?: string;
  [key: string]: unknown;
}

export function useTaskWebSocket(taskId: string | null) {
  const [events, setEvents] = useState<WsEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!taskId) return;
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/tasks/${taskId}`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data) as WsEvent;
        setEvents((prev) => [...prev, payload]);
      } catch {
        /* ignore non-JSON frames */
      }
    };

    return () => ws.close();
  }, [taskId]);

  return { events, connected };
}
