/**
 * Formato numérico local `es-CL` (RNF-15.a/b, §11.4). T52.
 * Miles con punto, decimal con coma; enteros sin decimales; variaciones con
 * signo explícito y porcentaje a 1 decimal.
 */

const integerFormatter = new Intl.NumberFormat("es-CL", {
  maximumFractionDigits: 0,
  minimumFractionDigits: 0,
});

const oneDecimalFormatter = new Intl.NumberFormat("es-CL", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** `184732` → `"184.732"`. */
export function formatInteger(value: number): string {
  return integerFormatter.format(value);
}

/** `3120` → `"+3.120"`; `-412` → `"−412"` (menos tipográfico); `0` → `"0"`. */
export function formatSignedInteger(value: number): string {
  if (value === 0) return "0";
  const sign = value > 0 ? "+" : "−";
  return `${sign}${integerFormatter.format(Math.abs(value))}`;
}

/** `1.71` → `"+1,7 %"`; `-13.95` → `"−14,0 %"`; `0` → `"0,0 %"`. */
export function formatSignedPercent(value: number): string {
  if (value === 0) return "0,0 %";
  const sign = value > 0 ? "+" : "−";
  return `${sign}${oneDecimalFormatter.format(Math.abs(value))} %`;
}

/** Porcentaje sin signo (para tooltips donde el signo lo aporta el glifo). */
export function formatPercent(value: number): string {
  return `${oneDecimalFormatter.format(value)} %`;
}

export type VariationTone = "pos" | "neg" | "flat";

export interface VariationParts {
  glyph: string;
  abs: string;
  pct: string;
  tone: VariationTone;
  /** Texto completo accesible: `"▲ +12 (+3,4 %)"`. */
  text: string;
}

/**
 * Variación con glifo + signo + porcentaje (RF-02.c, RF-04.f, RNF-09.d).
 * Nunca depende solo del color.
 */
export function formatVariation(
  deltaAbs: number | null,
  deltaPct: number | null,
): VariationParts | null {
  if (deltaAbs === null) return null;
  const tone: VariationTone = deltaAbs > 0 ? "pos" : deltaAbs < 0 ? "neg" : "flat";
  const glyph = tone === "pos" ? "▲" : tone === "neg" ? "▼" : "=";
  const abs = formatSignedInteger(deltaAbs);
  const pct = deltaPct === null ? "sin base" : `(${formatSignedPercent(deltaPct)})`;
  return { glyph, abs, pct, tone, text: `${glyph} ${abs} ${pct}` };
}

export function toneColorVar(tone: VariationTone): string {
  if (tone === "pos") return "var(--pos)";
  if (tone === "neg") return "var(--neg)";
  return "var(--neutral)";
}

/** Edad en formato `hace Xs` / `hace Xm` / `hace Xh` (RF-05.h). */
export function formatAge(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.floor(seconds))}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h`;
}

/** Fecha/hora local `es-CL` a partir de ISO-8601 (§RNF-15.a). */
export function formatLocalDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  try {
    return new Intl.DateTimeFormat("es-CL", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(date);
  } catch {
    return date.toISOString();
  }
}

/** Solo hora local `HH:MM:SS` para el reloj de cabecera. */
export function formatClock(date: Date): string {
  try {
    return new Intl.DateTimeFormat("es-CL", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(date);
  } catch {
    return date.toISOString().slice(11, 19);
  }
}
