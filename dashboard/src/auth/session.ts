/**
 * Sesión de auth nativa (T49, §2.2.2, RNF-03.a/b, RNF-13.b).
 *
 * El dashboard usa login **usuario+contraseña** contra `POST /auth/login` del
 * backend. No hay IdP externo, ni redirecciones, ni `client_secret` en el bundle.
 *
 * - El **access token** vive en MEMORIA.
 * - El **refresh token** se conserva en `sessionStorage` (ámbito de pestaña;
 *   se descarta al cerrar), nunca en `localStorage` (AM-12).
 * - Refresh **rotativo**: cada refresh guarda el nuevo token; si el servidor
 *   detecta reuso revoca la cadena y el cliente vuelve a login.
 * - Logout: limpia el estado local y llama a `POST /auth/logout`; el backend
 *   responde `Clear-Site-Data: "cache", "storage", "cookies"` (§2.2.5).
 * - Todas las peticiones de credenciales usan `cache: "no-store"` y no
 *   adjuntan cookies (`credentials: "omit"`).
 */

import { config } from "../config";

const REFRESH_KEY = "dash.auth.refresh";

export interface AuthSession {
  sub: string;
  accessToken: string;
  refreshToken: string | null;
  csrfToken: string | null;
  expiresAt: number;
  capabilities: string[];
  roles: string[];
}

interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  csrf_token?: string;
  expires_in?: number;
  token_type?: string;
  sub?: string;
  roles?: string[];
  capabilities?: string[];
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

/** Token anti-CSRF ligado a la sesión (AM-12, T63). */
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

function toSession(tokens: TokenResponse, previousRefresh: string | null): AuthSession {
  const claims = decodeJwtClaims(tokens.access_token);
  const embeddedCaps = Array.isArray(claims.capabilities)
    ? (claims.capabilities as unknown[]).map(String)
    : [];
  const embeddedRoles = Array.isArray(claims.roles)
    ? (claims.roles as unknown[]).map(String)
    : [];
  const expiresIn = typeof tokens.expires_in === "number" ? tokens.expires_in : 900;
  return {
    sub: String(tokens.sub ?? claims.sub ?? ""),
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token ?? previousRefresh,
    csrfToken: tokens.csrf_token ?? null,
    expiresAt: Date.now() + expiresIn * 1000,
    capabilities: (tokens.capabilities ?? embeddedCaps).map(String),
    roles: (tokens.roles ?? embeddedRoles).map(String),
  };
}

function persistRefresh(token: string | null): void {
  if (token) sessionStorage.setItem(REFRESH_KEY, token);
  else sessionStorage.removeItem(REFRESH_KEY);
}

/** Login usuario+contraseña. Lanza si las credenciales no son válidas. */
export async function login(username: string, password: string): Promise<AuthSession> {
  const response = await fetch(`${config.apiBaseUrl}/auth/login`, {
    method: "POST",
    cache: "no-store",
    credentials: "omit",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw new Error("Credenciales inválidas o cuenta no disponible.");
  }
  const tokens = (await response.json()) as TokenResponse;
  session = toSession(tokens, tokens.refresh_token ?? null);
  persistRefresh(session.refreshToken);
  notify();
  return session;
}

/** Renueva el access token con refresh rotativo (guarda el nuevo refresh). */
export async function refreshAccessToken(): Promise<AuthSession | null> {
  const refreshToken = session?.refreshToken ?? sessionStorage.getItem(REFRESH_KEY);
  if (!refreshToken) return null;
  const response = await fetch(`${config.apiBaseUrl}/auth/refresh`, {
    method: "POST",
    cache: "no-store",
    credentials: "omit",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    // Reuse detection / expiración → limpiar y volver a autenticar.
    clearSession();
    return null;
  }
  const tokens = (await response.json()) as TokenResponse;
  session = toSession(tokens, tokens.refresh_token ?? refreshToken);
  persistRefresh(session.refreshToken);
  notify();
  return session;
}

export function clearSession(): void {
  session = null;
  persistRefresh(null);
  notify();
}

/** Logout: limpia el estado local y revoca la sesión en el backend. */
export async function logout(): Promise<void> {
  const refreshToken = session?.refreshToken ?? sessionStorage.getItem(REFRESH_KEY);
  clearSession();
  try {
    await fetch(`${config.apiBaseUrl}/auth/logout`, {
      method: "POST",
      cache: "no-store",
      credentials: "omit",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(refreshToken ? { refresh_token: refreshToken } : {}),
    });
  } catch {
    /* sin red: la sesión local ya quedó limpia */
  }
}

/** Garantiza un access token vigente (renueva si está por expirar). */
export async function ensureFreshToken(): Promise<string | null> {
  if (!session) return null;
  if (session.expiresAt - Date.now() > 30_000) return session.accessToken;
  const renewed = await refreshAccessToken();
  return renewed?.accessToken ?? null;
}
