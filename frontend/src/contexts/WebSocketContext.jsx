import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { wsUrl } from "../lib/api";
import { useAuth } from "./AuthContext";

const WSContext = createContext(null);

export function DashboardSocketProvider({ children }) {
  const { accessToken, isAuthenticated } = useAuth();
  const [status, setStatus] = useState("disconnected"); // connecting|connected|disconnected
  const wsRef = useRef(null);
  const listenersRef = useRef(new Set());
  const backoffRef = useRef(1000);
  const stopRef = useRef(false);

  const subscribe = useCallback((fn) => {
    listenersRef.current.add(fn);
    return () => listenersRef.current.delete(fn);
  }, []);

  const emit = useCallback((msg) => {
    listenersRef.current.forEach((fn) => {
      try {
        fn(msg);
      } catch (e) {
        // ignore listener errors
      }
    });
  }, []);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      if (wsRef.current) {
        stopRef.current = true;
        wsRef.current.close();
        wsRef.current = null;
      }
      setStatus("disconnected");
      return;
    }

    stopRef.current = false;

    const connect = () => {
      const url = wsUrl(`/ws/dashboard?token=${encodeURIComponent(accessToken)}`);
      setStatus("connecting");
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = () => {
        setStatus("connected");
        backoffRef.current = 1000;
      };
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          emit(data);
        } catch {
          // ignore malformed
        }
      };
      ws.onclose = () => {
        setStatus("disconnected");
        if (stopRef.current) return;
        const delay = Math.min(backoffRef.current, 15000);
        setTimeout(connect, delay);
        backoffRef.current = Math.min(backoffRef.current * 2, 15000);
      };
      ws.onerror = () => {
        try {
          ws.close();
        } catch {}
      };
    };
    connect();
    return () => {
      stopRef.current = true;
      if (wsRef.current) {
        try { wsRef.current.close(); } catch {}
      }
    };
  }, [accessToken, isAuthenticated, emit]);

  return (
    <WSContext.Provider value={{ status, subscribe }}>
      {children}
    </WSContext.Provider>
  );
}

export function useDashboardSocket() {
  const ctx = useContext(WSContext);
  if (!ctx) throw new Error("useDashboardSocket must be within DashboardSocketProvider");
  return ctx;
}
