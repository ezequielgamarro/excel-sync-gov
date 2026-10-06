/**
 * Banners de estado global: DATOS DESACTUALIZADOS, ACTUALIZACIÓN REQUERIDA
 * (esquema) y DATOS NO VÁLIDOS (fail-closed). No dependen solo del color:
 * llevan glifo y texto.
 */

import { formatAge } from "../lib/format";

export function StaleBanner({ ageSeconds }: { ageSeconds: number }): JSX.Element {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-2 rounded-[12px] border border-warn/50 bg-warn/10 px-4 py-2 text-sm font-semibold text-warn"
    >
      <span aria-hidden="true">⚠</span>
      <span>DATOS DESACTUALIZADOS — hace {formatAge(ageSeconds)}</span>
    </div>
  );
}

export function SchemaErrorBanner(): JSX.Element {
  return (
    <div
      role="alert"
      className="flex items-center gap-2 rounded-[12px] border border-neg/50 bg-neg/10 px-4 py-2 text-sm font-semibold text-neg"
    >
      <span aria-hidden="true">⛔</span>
      <span>ACTUALIZACIÓN REQUERIDA — versión de esquema no soportada</span>
    </div>
  );
}

export function InvalidDataBanner({ detail }: { detail?: string }): JSX.Element {
  return (
    <div
      role="alert"
      className="flex items-center gap-2 rounded-[12px] border border-neg/50 bg-neg/10 px-4 py-2 text-sm font-semibold text-neg"
    >
      <span aria-hidden="true">⛔</span>
      <span>
        DATOS NO VÁLIDOS — se rechazó la instantánea completa
        {detail ? <span className="font-normal"> ({detail})</span> : null}
      </span>
    </div>
  );
}

export function PartialDataNotice(): JSX.Element {
  return (
    <p className="text-xs text-muted" role="status">
      Aviso: datos parciales en origen (quality.partial = true).
    </p>
  );
}
