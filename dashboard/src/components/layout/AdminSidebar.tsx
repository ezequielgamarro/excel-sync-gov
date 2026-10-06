import { useEffect } from "react";
import { DESKTOP_MEDIA_QUERY, useMediaQuery } from "../../hooks/useMediaQuery";

export interface AdminSection {
  id: string;
  label: string;
}

export const ADMIN_SECTIONS: readonly AdminSection[] = [
  { id: "resumen", label: "Resumen General" },
  { id: "incidentes", label: "Incidentes Operativos" },
  { id: "logistica", label: "Logística / Vehículos" },
  { id: "estadisticas", label: "Estadísticas / Distribución" },
  { id: "hospitales", label: "Ingresos Hospitalarios" },
  { id: "comparativas", label: "Comparativas" },
];

function SectionIcon({ id }: { id: string }): JSX.Element {
  switch (id) {
    case "resumen":
      return (
        <svg
          viewBox="0 0 24 24"
          width={18}
          height={18}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.7}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <rect x="3" y="3" width="7" height="9" rx="1" />
          <rect x="14" y="3" width="7" height="5" rx="1" />
          <rect x="14" y="12" width="7" height="9" rx="1" />
          <rect x="3" y="16" width="7" height="5" rx="1" />
        </svg>
      );
    case "incidentes":
      return (
        <svg
          viewBox="0 0 24 24"
          width={18}
          height={18}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.7}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M12 3l9 16H3z" />
          <path d="M12 9v4" />
          <path d="M12 16.5h.01" />
        </svg>
      );
    case "logistica":
      return (
        <svg
          viewBox="0 0 24 24"
          width={18}
          height={18}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.7}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M3 7h11v8H3z" />
          <path d="M14 10h4l3 3v2h-7z" />
          <circle cx="7" cy="17" r="1.6" />
          <circle cx="17.5" cy="17" r="1.6" />
        </svg>
      );
    case "estadisticas":
      return (
        <svg
          viewBox="0 0 24 24"
          width={18}
          height={18}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.7}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M4 20V10" />
          <path d="M10 20V4" />
          <path d="M16 20v-7" />
          <path d="M22 20V8" />
        </svg>
      );
    case "hospitales":
      // Cruz médica con pulso (ingresos hospitalarios).
      return (
        <svg
          viewBox="0 0 24 24"
          width={18}
          height={18}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.7}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M10 3h4v5h5v4h-5v5h-4v-5H5V8h5z" />
          <path d="M3 20h2l1.5-3 3 5 2-3H21" />
        </svg>
      );
    default:
      return (
        <svg
          viewBox="0 0 24 24"
          width={18}
          height={18}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.7}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M4 6h16" />
          <path d="M4 12h16" />
          <path d="M4 18h10" />
        </svg>
      );
  }
}

export interface AdminSidebarProps {
  activeTab: string;
  onSelect: (id: string) => void;
  /** Estado del drawer en pantallas < lg (ignorado en escritorio). */
  open?: boolean;
  /** Cierra el drawer (overlay, Escape o selección de sección). */
  onClose?: () => void;
}

/**
 * Sidebar táctico con la navegación principal del panel.
 *
 * - En pantallas `lg` o mayores es una columna fija.
 * - Por debajo de `lg` funciona como drawer off-canvas controlado por
 *   `open`/`onClose`, con overlay, cierre con Escape y `aria-hidden` cuando
 *   está cerrado.
 */
export function AdminSidebar({
  activeTab,
  onSelect,
  open = false,
  onClose,
}: AdminSidebarProps): JSX.Element {
  const isDesktop = useMediaQuery(DESKTOP_MEDIA_QUERY);
  const drawerOpen = isDesktop || open;

  useEffect(() => {
    if (isDesktop || !open || !onClose) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isDesktop, open, onClose]);

  return (
    <>
      {!isDesktop && open ? (
        <div
          className="fixed inset-0 z-30 bg-night/70 backdrop-blur-sm lg:hidden"
          onClick={onClose}
          aria-hidden="true"
          data-testid="sidebar-overlay"
        />
      ) : null}

      <aside
        id="admin-sidebar"
        aria-label="Navegación principal"
        aria-hidden={!drawerOpen}
        className={`admin-sidebar fixed inset-y-0 left-0 z-40 flex h-full w-[240px] shrink-0 flex-col border-r border-border bg-surface shadow-raise transition-transform duration-200 ease-out lg:static lg:z-auto lg:translate-x-0 lg:shadow-none ${
          drawerOpen ? "translate-x-0" : "-translate-x-full pointer-events-none"
        }`}
      >
        <div className="flex items-center gap-3 border-b border-border px-5 py-4">
          <img
            src={`${import.meta.env.BASE_URL}icons/logo-policia-tucuman.png`}
            alt="Policía de Tucumán"
            className="h-10 w-10 shrink-0 object-contain"
            width={40}
            height={40}
          />
          <div className="flex min-w-0 flex-col leading-tight">
            <span
              className="font-display text-sm font-semibold uppercase tracking-[0.06em] text-accent"
              translate="no"
            >
              Policía de Tucumán
            </span>
            <span className="truncate text-[10px] uppercase tracking-[0.06em] text-muted">
              Centro Integrador de Sistemas
            </span>
          </div>
        </div>

        <nav
          aria-label="Secciones del panel"
          className="flex flex-1 flex-col gap-1 overflow-y-auto p-3"
        >
          {ADMIN_SECTIONS.map((section) => {
            const active = section.id === activeTab;
            return (
              <button
                key={section.id}
                type="button"
                onClick={() => onSelect(section.id)}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-3 rounded-[10px] border px-3 py-2 text-left text-sm font-medium transition-colors ${
                  active
                    ? "border-accent/60 bg-accent-soft text-accent shadow-[0_0_14px_-4px_rgba(76,194,255,0.8)]"
                    : "border-transparent text-ink2 hover:border-border hover:bg-surface2 hover:text-ink"
                }`}
              >
                <span className={active ? "text-accent" : "text-muted"}>
                  <SectionIcon id={section.id} />
                </span>
                <span className="truncate">{section.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="flex flex-col gap-1 border-t border-border p-3">
          <span className="px-2 pb-1 text-[10px] uppercase tracking-[0.12em] text-muted">
            Preferencias
          </span>
          <button
            type="button"
            onClick={() => onSelect("ayuda")}
            aria-current={activeTab === "ayuda" ? "page" : undefined}
            className={`flex items-center gap-3 rounded-[10px] border px-3 py-2 text-left text-sm transition-colors ${
              activeTab === "ayuda"
                ? "border-accent/60 bg-accent-soft text-accent shadow-[0_0_14px_-4px_rgba(76,194,255,0.8)]"
                : "border-transparent text-ink2 hover:border-border hover:bg-surface2 hover:text-ink"
            }`}
          >
            <svg
              viewBox="0 0 24 24"
              width={18}
              height={18}
              fill="none"
              stroke="currentColor"
              strokeWidth={1.7}
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="9" />
              <path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7" />
              <path d="M12 17h.01" />
            </svg>
            Ayuda
          </button>
        </div>
      </aside>
    </>
  );
}
