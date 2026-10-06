import { useEffect, useRef } from "react";

const LINK_DIST = 140;
const LINK_DIST_SQ = LINK_DIST * LINK_DIST;
const MAX_DPR = 1.5;
const NODE_COLOR = "#5161ff"; // --police-blue-bright
const ACCENT_COLOR = "#4cc2ff"; // cian (~20% de los nodos)
const TAU = Math.PI * 2;

interface Field {
  count: number;
  x: Float32Array;
  y: Float32Array;
  vx: Float32Array;
  vy: Float32Array;
  r: Float32Array;
  accent: Uint8Array;
}

/** Construye el campo de partículas (única fase con allocaciones). */
function buildField(w: number, h: number): Field {
  const count = Math.max(90, Math.min(170, Math.round((w * h) / 11000)));
  const x = new Float32Array(count);
  const y = new Float32Array(count);
  const vx = new Float32Array(count);
  const vy = new Float32Array(count);
  const r = new Float32Array(count);
  const accent = new Uint8Array(count);
  for (let i = 0; i < count; i += 1) {
    x[i] = Math.random() * w;
    y[i] = Math.random() * h;
    vx[i] = (Math.random() - 0.5) * 0.5; // ±0.25 px/frame
    vy[i] = (Math.random() - 0.5) * 0.5;
    r[i] = 1 + Math.random(); // radio 1..2 px
    accent[i] = Math.random() < 0.2 ? 1 : 0;
  }
  return { count, x, y, vx, vy, r, accent };
}

/** Fondo ambiental: red de partículas neón conectadas (solo decorativo). */
export function CyberBackdrop(): JSX.Element {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let width = 0;
    let height = 0;
    let field = buildField(1, 1);
    let raf = 0;

    const draw = (): void => {
      context.clearRect(0, 0, width, height);
      const { count, x, y, r, accent } = field;

      context.lineWidth = 1;
      context.strokeStyle = NODE_COLOR;
      for (let i = 0; i < count; i += 1) {
        for (let j = i + 1; j < count; j += 1) {
          const dx = x[j] - x[i];
          const dy = y[j] - y[i];
          const d2 = dx * dx + dy * dy;
          if (d2 >= LINK_DIST_SQ) continue;
          const dist = Math.sqrt(d2);
          context.globalAlpha = 1 - dist / LINK_DIST;
          context.beginPath();
          context.moveTo(x[i], y[i]);
          context.lineTo(x[j], y[j]);
          context.stroke();
        }
      }

      context.globalAlpha = 1;
      for (let i = 0; i < count; i += 1) {
        context.beginPath();
        context.arc(x[i], y[i], r[i], 0, TAU);
        context.fillStyle = accent[i] ? ACCENT_COLOR : NODE_COLOR;
        context.fill();
      }
    };

    const step = (): void => {
      const { count, x, y, vx, vy } = field;
      for (let i = 0; i < count; i += 1) {
        let nx = x[i] + vx[i];
        let ny = y[i] + vy[i];
        if (nx < 0) {
          nx = 0;
          vx[i] = -vx[i];
        } else if (nx > width) {
          nx = width;
          vx[i] = -vx[i];
        }
        if (ny < 0) {
          ny = 0;
          vy[i] = -vy[i];
        } else if (ny > height) {
          ny = height;
          vy[i] = -vy[i];
        }
        x[i] = nx;
        y[i] = ny;
      }
      draw();
    };

    const loop = (): void => {
      step();
      raf = window.requestAnimationFrame(loop);
    };

    const resize = (): void => {
      width = host.clientWidth || window.innerWidth;
      height = host.clientHeight || window.innerHeight;
      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      field = buildField(width, height);
      if (reduced) draw();
    };

    const onVisibility = (): void => {
      if (reduced) return;
      if (document.hidden) {
        if (raf) {
          window.cancelAnimationFrame(raf);
          raf = 0;
        }
      } else if (!raf) {
        raf = window.requestAnimationFrame(loop);
      }
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    document.addEventListener("visibilitychange", onVisibility);
    if (!reduced) raf = window.requestAnimationFrame(loop);

    return () => {
      if (raf) window.cancelAnimationFrame(raf);
      observer.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <div ref={hostRef} className="cyber-backdrop" aria-hidden="true">
      <canvas ref={canvasRef} className="cyber-backdrop__canvas" aria-hidden="true" />
    </div>
  );
}
