import { useEffect, useRef, useState } from "react";

export type WSState = "connecting" | "open" | "closed" | "error";

interface UseWebSocketOptions {
  url: string;
  enabled?: boolean;
  onMessage?: (data: unknown) => void;
  reconnectDelay?: number;
  maxReconnectDelay?: number;
}

/**
 * Hook WebSocket avec auto-reconnect + backoff exponentiel.
 * Retourne l'etat de la connexion + les derniers messages.
 */
export function useWebSocket<T = unknown>({
  url, enabled = true, onMessage, reconnectDelay = 1000,
  maxReconnectDelay = 30_000,
}: UseWebSocketOptions) {
  const [state, setState] = useState<WSState>("closed");
  const [messages, setMessages] = useState<T[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const delayRef = useRef(reconnectDelay);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    if (!enabled) return;

    function connect() {
      if (!mountedRef.current) return;
      setState("connecting");
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setState("open");
        delayRef.current = reconnectDelay;
      };
      ws.onmessage = (ev) => {
        let data: unknown = ev.data;
        try { data = JSON.parse(ev.data); } catch { /* raw string OK */ }
        setMessages((prev) => [...prev.slice(-199), data as T]);
        onMessage?.(data);
      };
      ws.onerror = () => setState("error");
      ws.onclose = () => {
        setState("closed");
        if (!mountedRef.current) return;
        const nextDelay = Math.min(delayRef.current * 2, maxReconnectDelay);
        delayRef.current = nextDelay;
        timerRef.current = setTimeout(connect, nextDelay);
      };
    }
    connect();

    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, [url, enabled, onMessage, reconnectDelay, maxReconnectDelay]);

  function send(data: unknown) {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(typeof data === "string" ? data : JSON.stringify(data));
    }
  }

  return { state, messages, send };
}
