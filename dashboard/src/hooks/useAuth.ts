/**
 * Hook de autenticación nativa (T49, §2.2.2). Expone la sesión/capacidades y el
 * login usuario+contraseña. Sin redirecciones ni IdP externo.
 */

import { useCallback, useEffect, useState } from "react";
import {
  getSession,
  hasCapability,
  login as loginRequest,
  logout as logoutRequest,
  refreshAccessToken,
  subscribeAuth,
  type AuthSession,
} from "../auth/session";

export type AuthStatus = "checking" | "anonymous" | "authenticated" | "error";

export interface AuthState {
  status: AuthStatus;
  session: AuthSession | null;
  error: string | null;
  submitting: boolean;
  canViewLive: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

export function useAuth(): AuthState {
  const [status, setStatus] = useState<AuthStatus>("checking");
  const [session, setSession] = useState<AuthSession | null>(getSession());
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const unsubscribe = subscribeAuth((next) => {
      if (!cancelled) setSession(next);
    });

    (async () => {
      if (getSession()) {
        if (!cancelled) setStatus("authenticated");
        return;
      }
      // Intenta restaurar la sesión con el refresh de la pestaña (si existe).
      try {
        const restored = await refreshAccessToken();
        if (cancelled) return;
        setStatus(restored ? "authenticated" : "anonymous");
      } catch {
        if (!cancelled) setStatus("anonymous");
      }
    })();

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const next = await loginRequest(username, password);
      setSession(next);
      setStatus("authenticated");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("anonymous");
    } finally {
      setSubmitting(false);
    }
  }, []);

  const logout = useCallback(() => {
    void logoutRequest().finally(() => {
      setSession(null);
      setStatus("anonymous");
    });
  }, []);

  return {
    status,
    session,
    error,
    submitting,
    // Si el token no trae el claim `capabilities`, no se decide en cliente: se
    // deja que el backend aplique RBAC (P6) y responda 403.
    canViewLive:
      Boolean(session) && (session!.capabilities.length === 0 || hasCapability("dash.view.live")),
    login,
    logout,
  };
}
