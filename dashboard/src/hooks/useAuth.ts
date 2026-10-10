/**
 * Hook de autenticación nativa (T49, §2.2.2). Expone la sesión/capacidades y el
 * login usuario+contraseña. Sin redirecciones ni IdP externo.
 */

import { useCallback, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "../supabaseClient";
import {
  getSession,
  hasCapability,
  login as loginRequest,
  logout as logoutRequest,
  subscribeAuth,
  syncSupabaseSession,
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

    // Sincroniza el estado local con una sesión de Supabase (o su ausencia).
    const aplicar = (supaSession: Session | null) => {
      if (cancelled) return;
      const next = syncSupabaseSession(supaSession);
      setSession(next);
      setStatus((current) => {
        if (next) return "authenticated";
        // No pisa la comprobación inicial mientras se restaura la sesión.
        return current === "checking" ? current : "anonymous";
      });
    };

    // Mantiene sincronizado el estado ante login/logout/refresh forzados desde
    // otras partes del módulo de sesión.
    const unsubscribe = subscribeAuth((next) => {
      if (cancelled) return;
      setSession(next);
      setStatus((current) => {
        if (next) return "authenticated";
        return current === "checking" ? current : "anonymous";
      });
    });

    // Estado inicial: sesión persistida por Supabase (localStorage).
    void supabase.auth.getSession().then(({ data }) => {
      if (cancelled) return;
      const next = syncSupabaseSession(data.session);
      setSession(next);
      setStatus(next ? "authenticated" : "anonymous");
    });

    // Fuente de verdad: listener nativo de Supabase Auth.
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, supaSession) => {
      aplicar(supaSession);
    });

    return () => {
      cancelled = true;
      unsubscribe();
      subscription.unsubscribe();
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
    // deja que Supabase (RLS) aplique la autorización y responda sin acceso.
    canViewLive:
      Boolean(session) && (session!.capabilities.length === 0 || hasCapability("dash.view.live")),
    login,
    logout,
  };
}
