/** Skeletons de carga (§11.5): nunca ceros inventados (RF-02.h, CA-05.5). */

export function Skeleton({ className = "" }: { className?: string }): JSX.Element {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

export function KpiSkeleton(): JSX.Element {
  return (
    <div
      className="kpi-card flex flex-col justify-between"
      style={{ height: "var(--kpi-row-height)" }}
      aria-hidden="true"
    >
      <Skeleton className="h-3 w-3/4" />
      <Skeleton className="h-9 w-1/2" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  );
}

export function ChartSkeleton({ title }: { title: string }): JSX.Element {
  return (
    <div className="panel h-full" role="status" aria-label={`Cargando ${title}…`}>
      <Skeleton className="mb-6 h-4 w-1/2" />
      <div className="space-y-4">
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-5/6" />
        <Skeleton className="h-6 w-3/4" />
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-6 w-1/2" />
      </div>
    </div>
  );
}

export function TableSkeleton(): JSX.Element {
  return (
    <div className="panel h-full" role="status" aria-label="Cargando ranking…">
      <Skeleton className="mb-6 h-4 w-1/3" />
      <div className="space-y-4">
        {Array.from({ length: 5 }).map((_, index) => (
          <Skeleton key={index} className="h-8 w-full" />
        ))}
      </div>
    </div>
  );
}
