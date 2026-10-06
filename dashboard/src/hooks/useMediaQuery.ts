/**
 * Suscripción a una media query CSS (p. ej. `(min-width: 1024px)`).
 *
 * - En navegador usa `window.matchMedia` y reacciona a los cambios de tamaño.
 * - En entornos sin `matchMedia` (jsdom en tests) devuelve `true`, de modo que
 *   el layout se comporta como escritorio y los tests no necesitan stubs.
 */

import { useEffect, useState } from "react";

function currentMatch(query: string): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return true;
  }
  return window.matchMedia(query).matches;
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => currentMatch(query));

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mediaQueryList = window.matchMedia(query);
    const onChange = (): void => setMatches(mediaQueryList.matches);
    onChange();
    mediaQueryList.addEventListener("change", onChange);
    return () => mediaQueryList.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** Breakpoint `lg` de Tailwind: a partir de aquí el sidebar es fijo. */
export const DESKTOP_MEDIA_QUERY = "(min-width: 1024px)";
