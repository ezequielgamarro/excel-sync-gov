/**
 * Animación de recuento (RF-02.g) y detección de `prefers-reduced-motion`
 * (RF-05.i). La animación dura 400 ms con easing `ease-out`; si el valor no
 * cambia, no se anima ni se toca el DOM visible (idempotencia visual, RF-02.f).
 */

import { useEffect, useRef, useState } from "react";

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handler = () => setReduced(mql.matches);
    mql.addEventListener?.("change", handler);
    return () => mql.removeEventListener?.("change", handler);
  }, []);

  return reduced;
}

export interface AnimatedNumberOptions {
  duration?: number;
  disabled?: boolean;
}

export function useAnimatedNumber(
  target: number,
  { duration = 400, disabled = false }: AnimatedNumberOptions = {},
): number {
  const [display, setDisplay] = useState(target);
  const displayRef = useRef(target);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    const from = displayRef.current;
    if (disabled || target === from) {
      displayRef.current = target;
      setDisplay(target);
      return;
    }

    let startTime: number | null = null;
    const step = (time: number) => {
      if (startTime === null) startTime = time;
      const progress = Math.min(1, (time - startTime) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      const value = Math.round(from + (target - from) * eased);
      displayRef.current = value;
      setDisplay(value);
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(step);
      } else {
        displayRef.current = target;
        setDisplay(target);
        frameRef.current = null;
      }
    };
    frameRef.current = requestAnimationFrame(step);

    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    };
  }, [target, duration, disabled]);

  return display;
}
