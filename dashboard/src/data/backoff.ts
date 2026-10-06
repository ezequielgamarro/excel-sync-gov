/**
 * Backoff exponencial con jitter para la reconexión del WSS (T50, RNF-05.a).
 * Secuencia base: 1, 2, 4, 8, 16, 30 s (tope 30 s), jitter ±20 %.
 */

export const BACKOFF_SECONDS = [1, 2, 4, 8, 16, 30] as const;

export function baseBackoffSeconds(attempt: number): number {
  if (attempt <= 0) return BACKOFF_SECONDS[0];
  const index = Math.min(attempt - 1, BACKOFF_SECONDS.length - 1);
  return BACKOFF_SECONDS[index];
}

/**
 * Devuelve el retardo en ms para el intento dado, con jitter ±20 %.
 * `random` es inyectable para pruebas deterministas.
 */
export function backoffDelayMs(attempt: number, random: () => number = Math.random): number {
  const base = baseBackoffSeconds(attempt) * 1000;
  const jitter = (random() * 2 - 1) * 0.2; // [-0.2, +0.2]
  return Math.round(base * (1 + jitter));
}
