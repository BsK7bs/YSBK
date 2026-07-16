import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, setAccessToken, setOnUnauthorized, setRefreshHandler } from "../lib/api";

const AuthContext = createContext(null);

const STORAGE_KEY = "dtp_session_v1";

function loadStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function saveStored(session) {
  if (session) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => loadStored());
  const [initializing, setInitializing] = useState(true);
  const sessionRef = useRef(session);
  sessionRef.current = session;

  const applySession = useCallback((next) => {
    setSession(next);
    sessionRef.current = next;
    saveStored(next);
    setAccessToken(next?.access_token || null);
  }, []);

  const logout = useCallback(async () => {
    const s = sessionRef.current;
    if (s?.refresh_token) {
      try {
        await api.post("/auth/logout", { refresh_token: s.refresh_token });
      } catch {}
    }
    applySession(null);
  }, [applySession]);

  const login = useCallback(
    async (email, password, remember_me = false) => {
      const { data } = await api.post("/auth/login", { email, password, remember_me });
      applySession(data);
      return data;
    },
    [applySession],
  );

  const signup = useCallback(
    async (payload) => {
      const { data } = await api.post("/auth/signup", payload);
      applySession(data);
      return data;
    },
    [applySession],
  );

  const acceptInvitation = useCallback(
    async (token, full_name, password) => {
      const { data } = await api.post("/invitations/accept", { token, full_name, password });
      applySession(data);
      return data;
    },
    [applySession],
  );

  const refreshMe = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      const s = sessionRef.current;
      if (s) {
        const merged = { ...s, user: data.user, organization: data.organization };
        applySession(merged);
      }
      return data;
    } catch {
      return null;
    }
  }, [applySession]);

  // Register refresh + unauthorized handlers with the axios interceptor
  useEffect(() => {
    setRefreshHandler(async () => {
      const s = sessionRef.current;
      if (!s?.refresh_token) throw new Error("no refresh token");
      const { data } = await api.post("/auth/refresh", { refresh_token: s.refresh_token });
      const merged = { ...s, access_token: data.access_token };
      applySession(merged);
      return data.access_token;
    });
    setOnUnauthorized(() => {
      applySession(null);
    });
  }, [applySession]);

  // Bootstrap: set the token immediately, then verify /me
  useEffect(() => {
    (async () => {
      const s = sessionRef.current;
      if (s?.access_token) {
        setAccessToken(s.access_token);
        try {
          const { data } = await api.get("/auth/me");
          applySession({ ...s, user: data.user, organization: data.organization });
        } catch {
          applySession(null);
        }
      }
      setInitializing(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo(
    () => ({
      session,
      user: session?.user || null,
      organization: session?.organization || null,
      accessToken: session?.access_token || null,
      isAuthenticated: !!session?.access_token,
      initializing,
      login,
      signup,
      logout,
      refreshMe,
      acceptInvitation,
    }),
    [session, initializing, login, signup, logout, refreshMe, acceptInvitation],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
