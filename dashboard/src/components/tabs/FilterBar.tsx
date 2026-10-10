import { useId } from "react";
import { useFilters } from "../../state/FiltersContext";
import type { RangoFilter } from "../charts/filters";

/**
 * Fallback estático SÓLO si Supabase no devolvió `regionales_disponibles`.
 * El catálogo real (nombres oficiales) llega por el contexto de filtros.
 */
const UNIDAD_OPTIONS_FALLBACK: ReadonlyArray<{ value: string; label: string }> = [
  { value: "capital", label: "Capital" },
  { value: "sur", label: "Sur" },
  { value: "este", label: "Este" },
  { value: "oeste", label: "Oeste" },
  { value: "norte", label: "Norte" },
];

const RANGO_OPTIONS: ReadonlyArray<{ value: RangoFilter; label: string }> = [
  { value: "24h", label: "24 h" },
  { value: "7d", label: "7 días" },
  { value: "30d", label: "30 días" },
];

const SELECT_CLASS =
  "rounded-[10px] border border-border bg-surface2 px-3 py-2 text-sm text-ink focus-visible:border-accent";

export interface FilterBarProps {
  /** `inline` compacta las etiquetas en una sola línea (para cabeceras). */
  layout?: "stacked" | "inline";
}

/** Filtros globales (unidad regional dinámica, rango) consumidos del contexto. */
export function FilterBar({ layout = "stacked" }: FilterBarProps): JSX.Element {
  const { filters, setFilter, unidadesDisponibles } = useFilters();
  const baseId = useId();
  const fieldClass =
    layout === "inline"
      ? "flex items-center gap-1 whitespace-nowrap text-[11px] uppercase tracking-wide text-muted"
      : "flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted";

  // Valor = nombre oficial de Supabase; primera opción «Todas». Fallback estático
  // únicamente cuando la lista dinámica viene vacía.
  const unidadOptions: ReadonlyArray<{ value: string; label: string }> =
    unidadesDisponibles.length > 0
      ? [
          { value: "TODAS", label: "Todas" },
          ...unidadesDisponibles.map((unidad) => ({ value: unidad, label: unidad })),
        ]
      : [{ value: "TODAS", label: "Todas" }, ...UNIDAD_OPTIONS_FALLBACK];

  const unidadId = `${baseId}-filter-unidad`;
  const rangoId = `${baseId}-filter-rango`;

  return (
    <div className="flex flex-wrap items-center gap-3">
      <label htmlFor={unidadId} className={fieldClass}>
        Unidad Regional
        <select
          id={unidadId}
          className={SELECT_CLASS}
          value={filters.unidad}
          onChange={(event) => setFilter("unidad", event.target.value)}
        >
          {unidadOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label htmlFor={rangoId} className={fieldClass}>
        Rango
        <select
          id={rangoId}
          className={SELECT_CLASS}
          value={filters.rango}
          onChange={(event) => setFilter("rango", event.target.value)}
        >
          {RANGO_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
