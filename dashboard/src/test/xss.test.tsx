/**
 * T70 — XSS por celdas de Google Sheets (AM-06, CA-02.8/CA-03.3).
 *
 * React escapa por defecto; el dashboard **nunca** usa
 * `dangerouslySetInnerHTML`. Un payload malicioso en el nombre de una
 * comisaría/etiqueta se renderiza como **texto literal**, sin crear nodos
 * `script`/`img` ni ejecutar handlers.
 */

import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { RankingTable } from "../components/RankingTable";
import { RegionalChart } from "../components/RegionalChart";
import type { RankingItem, RegionalItem } from "../types";

const PAYLOAD = '<img src=x onerror="window.__xss=1"><script>window.__xss=1</script>';

describe("XSS vía celdas del origen (AM-06, T70)", () => {
  it("escapa el payload en el ranking sin crear nodos HTML", () => {
    const deps: RankingItem[] = [
      {
        puesto: 1,
        dependencia_id: "x",
        comisaria: PAYLOAD,
        intervenciones: 10,
        variacion_abs: 1,
        variacion_pct: 1,
        puesto_previo: 1,
      },
    ];
    const { container } = render(<RankingTable dependencias={deps} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    // El texto se muestra (escapado), no se interpreta como HTML.
    expect(container.textContent).toContain("<img src=x");
  });

  it("escapa una etiqueta regional maliciosa", () => {
    const regional: RegionalItem[] = [
      {
        unidad_id: "capital",
        label: PAYLOAD,
        intervenciones: 5,
        variacion_abs: 1,
        variacion_pct: 1,
        rank: 1,
      },
    ];
    const { container } = render(<RegionalChart regional={regional} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });
});
