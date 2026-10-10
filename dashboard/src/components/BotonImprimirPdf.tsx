/**
 * Botón «Imprimir / PDF»: abre la ventana de informe, donde se elige el rango de
 * fechas y los gráficos a imprimir. Desde ahí se abre el diálogo de impresión
 * del navegador («Guardar como PDF»).
 */

import { useState } from "react";
import { Printer } from "lucide-react";
import { InformeImpresion } from "./informe/InformeImpresion";

const BOTON_CLASS =
  "touch-target inline-flex items-center gap-2 rounded-[10px] border border-border bg-surface2 px-4 py-2 text-sm font-semibold text-accent transition-colors hover:border-accent hover:bg-accent/10";

export function BotonImprimirPdf(): JSX.Element {
  const [abierto, setAbierto] = useState(false);
  return (
    <>
      <button
        type="button"
        className={BOTON_CLASS}
        onClick={() => setAbierto(true)}
        aria-label="Imprimir o guardar como PDF"
      >
        <Printer size={16} aria-hidden="true" />
        Imprimir / PDF
      </button>
      {abierto ? <InformeImpresion onClose={() => setAbierto(false)} /> : null}
    </>
  );
}
