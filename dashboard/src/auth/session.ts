/**
 * Sesión de autenticación basada en **Supabase Auth**.
 *
 * El dashboard autentica usuario+contraseña con `supabase.auth` y deja que el
 * SDK gestione la persistencia y la renovación de la sesión (localStorage). Ya
 * no se mantienen tokens manualmente ni se llaman endpoints propios de
 * `/auth/login`, `/auth/refresh` o `/auth/logout`.
 *
 * - El **access token** se expone desde el estado en memoria, sincronizado con
 *   la sesión de Supabase.
 * - El **refresh** lo gestiona el SDK; `refreshAccessToken()` delega en él.
 * - Logout: `supabase.auth.signOut()` + limpieza del estado local.
 * - `csrfToken` se conserva por compatibilidad de firma, pero Supabase no usa
 *   anti-CSRF manual: siempre es `null`.
 */

import type { Session, User } from "@supabase/supabase-js";
import { supabase } from "../supabaseClient";
import { registrarEvento } from "../lib/auditoria";

export interface AuthSession {
  sub: string;
  accessToken: string;
  refreshToken: string | null;
  csrfToken: string | null;
  expiresAt: number;
  capabilities: string[];
  roles: string[];
}

let session: AuthSession | null = null;
const listeners = new Set<(s: AuthSession | null) => void>();

function notify(): void {
  for (const listener of listeners) listener(session);
}

export function subscribeAuth(listener: (s: AuthSession | null) => void): () => void {
  listeners.add(listener);
  listener(session);
  return () => listeners.delete(listener);
}

export function getSession(): AuthSession | null {
  return session;
}

export function getAccessToken(): string | null {
  return session?.accessToken ?? null;
}

/** Compatibilidad de firma: Supabase no usa token anti-CSRF manual. */
export function getCsrfToken(): string | null {
  return session?.csrfToken ?? null;
}

export function hasCapability(capability: string): boolean {
  return session?.capabilities.includes(capability) ?? false;
}

function decodeJwtClaims(token: string): Record<string, unknown> {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function toArray(value: unknown): string[] {
  return Array.isArray(value) ? (value as unknown[]).map(String) : [];
}

/** Traduce una sesión de Supabase al shape interno `AuthSession`. */
function mapSupabaseSession(supaSession: Session, user?: User | null): AuthSession {
  const accessToken = supaSession.access_token;
  const claims = decodeJwtClaims(accessToken);
  const capabilities = toArray(
    claims.capabilities ?? user?.app_metadata?.capabilities ?? user?.user_metadata?.capabilities,
  );
  const roles = toArray(claims.roles ?? user?.app_metadata?.roles ?? user?.user_metadata?.roles);
  const expiresAt = (supaSession.expires_at ?? Date.now() / 1000 + (supaSession.expires_in ?? 3600)) * 1000;
  return {
    sub: user?.id ?? String(claims.sub ?? ""),
    accessToken,
    refreshToken: supaSession.refresh_token ?? null,
    csrfToken: null,
    expiresAt,
    capabilities,
    roles,
  };
}

/**
 * Sincroniza el estado de módulo con una sesión de Supabase (o la limpia si es
 * `null`) y notifica a los suscriptores. Única fuente de verdad de la sesión
 * persistida.
 */
export function syncSupabaseSession(supaSession: Session | null): AuthSession | null {
  session = supaSession ? mapSupabaseSession(supaSession, supaSession.user) : null;
  notify();
  return session;
}

/** Login usuario+contraseña contra Supabase. Lanza si las credenciales fallan. */
export async function login(username: string, password: string): Promise<AuthSession> {
  const { data, error } = await supabase.auth.signInWithPassword({ email: username, password });
  if (error) throw new Error(error.message);
  if (!data.session) throw new Error("No se pudo establecer la sesión.");
  session = mapSupabaseSession(data.session, data.user);
  notify();
  void registrarEvento("login");
  return session;
}

/**
 * Restaura la sesión persistida por Supabase (arranque de la app). Devuelve la
 * sesión mapeada o `null` si no hay ninguna activa.
 */
export async function restoreSession(): Promise<AuthSession | null> {
  const { data } = await supabase.auth.getSession();
  return syncSupabaseSession(data.session);
}

/** Renueva la sesión delegando en el SDK de Supabase. */
export async function refreshAccessToken(): Promise<AuthSession | null> {
  const { data, error } = await supabase.auth.refreshSession();
  if (error || !data.session) {
    clearSession();
    return null;
  }
  session = mapSupabaseSession(data.session, data.session.user);
  notify();
  return session;
}

export function clearSession(): void {
  session = null;
  notify();
}

/**
 * Cierre forzado tras una sesión irrecuperable (401). Limpia el estado local y
 * notifica a los suscriptores; como `App.tsx` decide Login vs Dashboard por
 * estado, basta con limpiar la sesión. Además vacía el hash para salir de
 * cualquier vista protegida.
 */
export function forceLogout(): void {
  clearSession();
  window.location.hash = "";
}

/** Logout: cierra la sesión en Supabase y limpia el estado local. */
export async function logout(): Promise<void> {
  try {
    // Antes de cerrar: el evento necesita la sesión vigente.
    await registrarEvento("logout");
    await supabase.auth.signOut();
  } catch {
    /* sin red: la sesión local se limpia igualmente */
  }
  clearSession();
}

/** Garantiza un access token vigente (renueva si está por expirar). */
export async function ensureFreshToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  const current = data.session;
  if (!current) return null;
  const expiresAt = (current.expires_at ?? Date.now() / 1000 + (current.expires_in ?? 3600)) * 1000;
  if (expiresAt - Date.now() > 30_000) return current.access_token;
  const renewed = await refreshAccessToken();
  return renewed?.accessToken ?? null;
}
