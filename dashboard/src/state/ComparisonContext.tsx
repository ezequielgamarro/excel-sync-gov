import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { ComparisonPeriod } from "../lib/comparison";

export type { ComparisonPeriod } from "../lib/comparison";
export { COMPARISON_LABEL } from "../lib/comparison";

interface ComparisonContextValue {
  period: ComparisonPeriod;
  setPeriod: (period: ComparisonPeriod) => void;
}

const ComparisonContext = createContext<ComparisonContextValue | null>(null);

/** Estado global del selector "Comparar vs" (sincroniza KPI, ranking y gráficas). */
export function ComparisonProvider({ children }: { children: ReactNode }): JSX.Element {
  const [period, setPeriod] = useState<ComparisonPeriod>("ayer");
  const value = useMemo<ComparisonContextValue>(() => ({ period, setPeriod }), [period]);
  return <ComparisonContext.Provider value={value}>{children}</ComparisonContext.Provider>;
}

export function useComparison(): ComparisonContextValue {
  const context = useContext(ComparisonContext);
  if (!context) {
    throw new Error("useComparison debe usarse dentro de <ComparisonProvider>.");
  }
  return context;
}
