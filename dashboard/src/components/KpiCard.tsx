/**
 * Tarjeta KPI (VIS-01..04, RF-02).
 *
 * - Etiqueta institucional EXACTA (mapeo de presentación en el frontend).
 * - Valor actual 40 px tabular con animación de 400 ms `ease-out` (RF-02.g).
 * - Período actual vs período anterior (valor y delta absoluto).
 * - Variación con glifo + signo + porcentaje y color por dirección, sin
 *   depender solo del color (RF-02.c/e).
 * - Idempotencia visual: si el valor no cambia, no anima ni destella (RF-02.f).
 * - Borde de acento 600 ms al cambiar (RF-02.g).
 * - `aria-live="polite"` anuncia el nuevo valor una vez (RNF-09.f).
 */

import { useEffect, useRef, useState } from "react";
import type { Kpi, KpiKey, TableroCpiKey } from "../types";
import { KPI_LABEL, TABLERO_KPI_LABEL } from "../types";
import { KpiIcon } from "./KpiIcon";
import {
  formatInteger,
  formatSignedPercent,
  formatVariation,
  toneColorVar,
  type VariationParts,
} from "../lib/format";
import { useAnimatedNumber, usePrefersReducedMotion } from "../hooks/useAnimatedNumber";

export interface KpiCardProps {
  kpiKey: KpiKey | TableroCpiKey;
  kpi: Kpi;
  /** Atenúa la tarjeta cuando los datos superan el umbral de frescura (RF-05.h). */
  dimmed?: boolean;
  /** Etiqueta del período de comparación (p. ej. "Mes anterior"). */
  periodLabel?: string;
}

function lowerFirst(value: string): string {
  return value.charAt(0).toLowerCase() + value.slice(1);
}

function TrendChip({ variation, pct }: { variation: VariationParts; pct: string }): JSX.Element {
  return (
    <span
      className="num inline-flex shrink-0 items-baseline gap-1 text-sm font-semibold"
      style={{ color: toneColorVar(variation.tone) }}
    >
      <span aria-hidden="true" className="text-base leading-none">
        {variation.glyph}
      </span>
      {pct}
    </span>
  );
}

export function KpiCard({
  kpiKey,
  kpi,
  dimmed = false,
  periodLabel = "período anterior",
}: KpiCardProps): JSX.Element {
  const reducedMotion = usePrefersReducedMotion();
  const displayValue = useAnimatedNumber(kpi.value, { duration: 400, disabled: reducedMotion });
  const [flash, setFlash] = useState(false);
  const prevRef = useRef(kpi.value);

  useEffect(() => {
    if (prevRef.current === kpi.value) return;
    prevRef.current = kpi.value;
    if (reducedMotion) return;
    setFlash(true);
    const id = window.setTimeout(() => setFlash(false), 600);
    return () => window.clearTimeout(id);
  }, [kpi.value, reducedMotion]);

  const label =
    kpiKey in KPI_LABEL
      ? KPI_LABEL[kpiKey as KpiKey]
      : TABLERO_KPI_LABEL[kpiKey as TableroCpiKey];
  const variation = kpi.has_reference ? formatVariation(kpi.delta_abs, kpi.delta_pct) : null;
  const pct =
    kpi.delta_pct === null || !Number.isFinite(kpi.delta_pct)
      ? "—"
      : formatSignedPercent(kpi.delta_pct);
  const hasPrevious = kpi.has_reference && kpi.delta_abs !== null;
  const deltaAbs = kpi.delta_abs ?? 0;
  const periodoMinus = lowerFirst(periodLabel);
  const diffText =
    deltaAbs > 0
      ? `${formatInteger(deltaAbs)} más que el ${periodoMinus}`
      : deltaAbs < 0
        ? `${formatInteger(Math.abs(deltaAbs))} menos que el ${periodoMinus}`
        : `Igual que el ${periodoMinus}`;
  const diffClass = deltaAbs > 0 ? "text-green-400" : deltaAbs < 0 ? "text-red-400" : "text-muted";

  return (
    <article
      className={`kpi-card flex flex-col justify-between ${flash ? "flash" : ""} ${
        dimmed ? "stale-dim" : ""
      }`}
      style={{ height: "var(--kpi-row-height)" }}
      role="group"
      aria-label={`${label}, valor actual ${formatInteger(kpi.value)}, ${
        hasPrevious
          ? `${periodLabel} ${formatInteger(kpi.baseline_value)}, variación ${variation?.text ?? pct}`
          : `sin ${periodLabel}`
      }`}
      data-kpi={kpiKey}
    >
      <header className="flex items-start justify-between gap-2">
        <span className="flex min-w-0 items-start gap-2">
          <KpiIcon kpiKey={kpiKey} />
          <span
            className="label-eyebrow min-w-0 line-clamp-2 break-words text-xs leading-tight"
            title={label}
          >
            {label}
          </span>
        </span>
        {variation ? <TrendChip variation={variation} pct={pct} /> : null}
      </header>

      <span
        className="kpi-value text-[40px] font-semibold leading-[1.02] text-ink"
        aria-hidden="true"
      >
        {formatInteger(displayValue)}
      </span>

      {kpiKey === "total_intervenciones" ? (
        <span
          className="text-[11px] leading-tight text-muted"
          title="Suma de personas, vehículos y armas"
        >
          (Suma de personas, vehículos y armas)
        </span>
      ) : null}

      <footer className="flex items-end justify-between gap-2 text-xs">
        {hasPrevious && variation ? (
          <>
            <span className="text-muted">
              {periodLabel}{" "}
              <span className="num text-ink2">{formatInteger(kpi.baseline_value)}</span>
            </span>
            <span className={diffClass}>{diffText}</span>
          </>
        ) : (
          <span className="text-muted opacity-60">— sin {periodLabel}</span>
        )}
      </footer>

      <span className="sr-only" aria-live="polite">
        {label}: {formatInteger(kpi.value)}
        {hasPrevious
          ? `, ${periodLabel} ${formatInteger(kpi.baseline_value)}, variación ${variation?.text ?? pct}`
          : `, sin ${periodLabel}`}
      </span>
    </article>
  );
}
