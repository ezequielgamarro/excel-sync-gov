import type { CSSProperties } from "react";
import type { KpiKey, TableroCpiKey } from "../types";

const NEON_STYLE: CSSProperties = {
  color: "var(--accent)",
  filter: "drop-shadow(0 0 8px rgba(76, 194, 255, 0.8))",
};

// Documento con esquina doblada + lupa.
const DOCUMENTO_ICON = (
  <>
    <path d="M7 3h6l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
    <path d="M13 3v5h5" />
    <circle cx="15" cy="15.5" r="3" />
    <path d="M17.2 17.7l3.3 3.3" />
  </>
);

// Dos siluetas de personas (esposas/aprehensiones).
const PERSONAS_ICON = (
  <>
    <circle cx="9" cy="8" r="3" />
    <path d="M3 19a6 6 0 0 1 12 0" />
    <circle cx="17.5" cy="9" r="2.5" />
    <path d="M15 19a4.5 4.5 0 0 1 6.5-4" />
  </>
);

// Perfil de vehículo con ruedas.
const VEHICULO_ICON = (
  <>
    <path d="M4 13l1.7-4.4A2 2 0 0 1 7.6 7h8.8a2 2 0 0 1 1.9 1.6L20 13" />
    <rect x="3" y="13" width="18" height="4" rx="1" />
    <circle cx="7.5" cy="17.5" r="1.7" />
    <circle cx="16.5" cy="17.5" r="1.7" />
  </>
);

// Pistola de perfil minimalista.
const ARMA_ICON = (
  <>
    <path d="M3 8h13v3H8l-1.2 2.2H4.5L6 11H3z" />
    <path d="M16 8h4v3h-4" />
    <path d="M9 11h5l-1.8 6H8.2z" />
    <path d="M13 11v2h2" />
  </>
);

// Círculo con tilde (resultado positivo).
const POSITIVO_ICON = (
  <>
    <circle cx="12" cy="12" r="9" />
    <path d="M8 12.5l2.5 2.5L16 9.5" />
  </>
);

const ICONS: Record<KpiKey | TableroCpiKey, JSX.Element> = {
  // Contrato WSS (snapshot).
  total_consultas_sifcop: DOCUMENTO_ICON,
  personas_capturadas: PERSONAS_ICON,
  vehiculos_secuestrados: VEHICULO_ICON,
  armas_secuestradas: ARMA_ICON,
  // Tablero real (fuente Supabase `intervenciones_diarias`).
  total_intervenciones: DOCUMENTO_ICON,
  total_positivos: POSITIVO_ICON,
  consultas_personas: PERSONAS_ICON,
  consultas_vehiculos: VEHICULO_ICON,
  consultas_armas: ARMA_ICON,
  consultas_elementos: DOCUMENTO_ICON,
};

/** Ícono decorativo neón cian por KPI (SVG inline, sin dependencias). */
export function KpiIcon({ kpiKey }: { kpiKey: KpiKey | TableroCpiKey }): JSX.Element {
  return (
    <svg
      viewBox="0 0 24 24"
      width={24}
      height={24}
      aria-hidden="true"
      focusable="false"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0"
      style={NEON_STYLE}
    >
      {ICONS[kpiKey]}
    </svg>
  );
}
