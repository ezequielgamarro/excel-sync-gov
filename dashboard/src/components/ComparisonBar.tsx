import { COMPARISON_LABEL, COMPARISON_PERIODS } from "../lib/comparison";
import { useComparison } from "../state/ComparisonContext";

/** Control segmentado accesible para elegir el período de comparación (global). */
export interface ComparisonBarProps {
  /** Etiqueta accesible del grupo (para distinguir instancias en la misma vista). */
  ariaLabel?: string;
}

export function ComparisonBar({ ariaLabel = "Comparar versus" }: ComparisonBarProps): JSX.Element {
  const { period, setPeriod } = useComparison();
  return (
    <div className="flex items-center gap-2" role="radiogroup" aria-label={ariaLabel}>
      <span className="whitespace-nowrap text-[11px] uppercase tracking-wide text-muted">Comparar vs:</span>
      <div className="flex flex-wrap gap-1">
        {COMPARISON_PERIODS.map((option) => {
          const selected = option === period;
          return (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => setPeriod(option)}
              className={`touch-target rounded-full px-3 text-[11px] font-semibold uppercase tracking-wide transition-colors ${
                selected
                  ? "border border-accent bg-accent-soft text-accent"
                  : "border border-border text-ink2 hover:border-accent hover:text-accent"
              }`}
            >
              {COMPARISON_LABEL[option]}
            </button>
          );
        })}
      </div>
    </div>
  );
}
