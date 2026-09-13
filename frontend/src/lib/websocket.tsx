"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type TelemetryEvent = {
  type: string;
  session_id: string;
  payload: Record<string, unknown>;
  timestamp?: string;
};

type WebSocketContextValue = {
  sessionId: string;
  connected: boolean;
  events: TelemetryEvent[];
  sendGoal: (goal: string) => Promise<void>;
};

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const sessionId = useMemo(() => `session-${crypto.randomUUID()}`, []);
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<TelemetryEvent[]>([]);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const wsUrl = API_BASE.replace(/^http/, "ws");
    const socket = new WebSocket(`${wsUrl}/api/v1/telemetry/stream/${sessionId}`);
    socketRef.current = socket;

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onmessage = (message) => {
      try {
        const frame = JSON.parse(message.data) as TelemetryEvent;
        setEvents((prev) => [frame, ...prev].slice(0, 200));
      } catch {
        // Ignore malformed frames in boilerplate mode.
      }
    };

    return () => socket.close();
  }, [sessionId]);

  const sendGoal = useCallback(async (goal: string) => {
    await fetch(`${API_BASE}/api/v1/chat/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: goal }),
    });
  }, [sessionId]);

  const value = useMemo(
    () => ({ sessionId, connected, events, sendGoal }),
    [sessionId, connected, events, sendGoal],
  );

  return <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>;
}

export function useTelemetry() {
  const ctx = useContext(WebSocketContext);
  if (!ctx) {
    throw new Error("useTelemetry must be used within WebSocketProvider");
  }
  return ctx;
}
