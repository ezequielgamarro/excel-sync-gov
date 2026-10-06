import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { DEFAULT_FILTERS } from "../components/charts/filters";
import type { ActiveFilters } from "../components/charts/filters";

export type { ActiveFilters } from "../components/charts/filters";
export { DEFAULT_FILTERS } from "../components/charts/filters";

interface FiltersContextValue {
  filters: ActiveFilters;
  setFilters: (filters: ActiveFilters) => void;
  setFilter: (key: keyof ActiveFilters, value: string) => void;
  /** Unidades Regionales reales devueltas por el backend (selectores). */
  unidadesDisponibles: string[];
  setUnidadesDisponibles: (unidades: string[]) => void;
}

const FiltersContext = createContext<FiltersContextValue | null>(null);

/** Estado global de los filtros (Unidad Regional y Rango) y catálogo dinámico. */
export function FiltersProvider({ children }: { children: ReactNode }): JSX.Element {
  const [filters, setFilters] = useState<ActiveFilters>(DEFAULT_FILTERS);
  const [unidadesDisponibles, setUnidadesDisponiblesState] = useState<string[]>([]);

  const setFilter = useCallback((key: keyof ActiveFilters, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }) as ActiveFilters);
  }, []);

  // Estable por contenido: evita re-renders cuando el backend repite la lista.
  const setUnidadesDisponibles = useCallback((unidades: string[]) => {
    setUnidadesDisponiblesState((prev) =>
      prev.length === unidades.length && prev.every((unit, index) => unit === unidades[index])
        ? prev
        : unidades,
    );
  }, []);

  const value = useMemo<FiltersContextValue>(
    () => ({ filters, setFilters, setFilter, unidadesDisponibles, setUnidadesDisponibles }),
    [filters, setFilter, unidadesDisponibles, setUnidadesDisponibles],
  );

  return <FiltersContext.Provider value={value}>{children}</FiltersContext.Provider>;
}

export function useFilters(): FiltersContextValue {
  const context = useContext(FiltersContext);
  if (!context) {
    throw new Error("useFilters debe usarse dentro de <FiltersProvider>.");
  }
  return context;
}
