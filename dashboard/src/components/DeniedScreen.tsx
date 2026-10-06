/** Pantalla de acceso denegado sin revelar datos (RF-02.k). */

export function DeniedScreen(): JSX.Element {
  return (
    <main className="flex h-screen flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="font-display text-3xl font-semibold uppercase tracking-[0.06em] text-neg" role="alert">
        Acceso Denegado
      </h1>
      <p className="max-w-md text-sm text-muted">
        No posee la capacidad requerida para visualizar esta sala. Contacte al administrador de
        plataforma si cree que es un error.
      </p>
    </main>
  );
}
