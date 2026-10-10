/**
 * Cascada Jefatura regional → Dependencia de `FormularioIntervencion`.
 *
 * Verifica que la dependencia arranca deshabilitada, se habilita al elegir una
 * jefatura, lista exactamente las dependencias del catálogo, se recalcula y se
 * resetea al cambiar de jefatura, y que el submit entrega los valores elegidos.
 */

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import {
  DEPENDENCIAS_POR_REGIONAL,
  DIRECCIONES,
  UNIDADES_REGIONALES,
} from "../../data/dependencias";
import {
  FORM_INICIAL,
  FormularioIntervencion,
  type FormValuesIntervencion,
} from "./FormularioIntervencion";

function renderFormulario(
  valoresIniciales: FormValuesIntervencion = FORM_INICIAL,
  onSubmit = vi.fn(),
): { onSubmit: ReturnType<typeof vi.fn> } {
  render(
    <FormularioIntervencion valoresIniciales={valoresIniciales} onSubmit={onSubmit} />,
  );
  return { onSubmit };
}

function opcionesDe(select: HTMLElement): string[] {
  return Array.from(select.querySelectorAll("option"))
    .map((option) => (option as HTMLOptionElement).value)
    .filter((value) => value !== "");
}

describe("FormularioIntervencion (cascada regional/dependencia)", () => {
  it("arranca con Dependencia deshabilitada", () => {
    renderFormulario();
    expect(screen.getByLabelText(/dependencia/i)).toBeDisabled();
  });

  it("habilita Dependencia y lista las dependencias de la jefatura elegida", () => {
    renderFormulario();
    const jefatura = screen.getByLabelText(/jefatura regional/i);
    const dependencia = screen.getByLabelText(/dependencia/i);

    fireEvent.change(jefatura, { target: { value: "U.R. Norte" } });

    expect(dependencia).toBeEnabled();
    expect(opcionesDe(dependencia)).toEqual([
      ...DEPENDENCIAS_POR_REGIONAL["U.R. Norte"],
    ]);
  });

  it("expone las 5 Unidades Regionales reales y las 7 Direcciones", () => {
    renderFormulario();
    const jefatura = screen.getByLabelText(/jefatura regional/i);
    expect(opcionesDe(jefatura)).toEqual([...UNIDADES_REGIONALES, ...DIRECCIONES]);
  });

  it("Vehículo/Arma muestran su subtipo y habilitan el detalle; Elemento solo el detalle", () => {
    renderFormulario();
    const tipo = screen.getByLabelText(/tipo de consulta/i);
    expect(screen.queryByLabelText(/n° de serie/i)).toBeNull();

    fireEvent.change(tipo, { target: { value: "Vehículo" } });
    expect(opcionesDe(screen.getByLabelText(/tipo de vehículo/i))).toEqual([
      "Auto", "Moto", "Camioneta", "Trafic", "Otros",
    ]);
    expect(screen.queryByLabelText(/n° de serie/i)).toBeNull();
    fireEvent.change(screen.getByLabelText(/tipo de vehículo/i), { target: { value: "Moto" } });
    expect(screen.getByLabelText(/n° de serie/i)).toBeInTheDocument();

    fireEvent.change(tipo, { target: { value: "Arma de fuego" } });
    expect(screen.getByLabelText(/tipo de arma/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/n° de serie/i)).toBeNull();

    fireEvent.change(tipo, { target: { value: "Elemento" } });
    expect(screen.getByLabelText(/n° de serie/i)).toBeInTheDocument();
  });

  it("Causas es desplegable solo con Persona + Positivo; si no, texto libre", () => {
    renderFormulario();
    expect(screen.getByLabelText(/^causas/i).tagName).toBe("INPUT");

    fireEvent.change(screen.getByLabelText(/tipo de consulta/i), { target: { value: "Persona" } });
    fireEvent.change(screen.getByLabelText(/^resultado$/i), { target: { value: "Positivo" } });
    expect(screen.getByLabelText(/^causas/i).tagName).toBe("SELECT");
    expect(opcionesDe(screen.getByLabelText(/^causas/i))).toHaveLength(6);

    fireEvent.change(screen.getByLabelText(/^resultado$/i), { target: { value: "Negativo" } });
    expect(screen.getByLabelText(/^causas/i).tagName).toBe("INPUT");
  });

  it("una Dirección deshabilita Dependencia (no tiene divisiones)", () => {
    renderFormulario();
    fireEvent.change(screen.getByLabelText(/jefatura regional/i), {
      target: { value: "D.G.U.E" },
    });
    expect(screen.getByLabelText(/dependencia/i)).toBeDisabled();
  });

  it("lista la cascada ESTRICTA: solo las dependencias de la jefatura elegida", () => {
    renderFormulario();
    const jefatura = screen.getByLabelText(/jefatura regional/i);
    const dependencia = screen.getByLabelText(/dependencia/i);

    fireEvent.change(jefatura, { target: { value: "U.R. Capital" } });
    expect(opcionesDe(dependencia)).toEqual([
      ...DEPENDENCIAS_POR_REGIONAL["U.R. Capital"],
    ]);
    expect(opcionesDe(dependencia)).toEqual([
      "Comisaría 1",
      "Comisaría 2",
      "Comisaría 3",
      "Comisaría 4",
      "Comisaría 5",
      "Comisaría 6",
      "Comisaría 7",
      "Comisaría 8",
      "Comisaría 9",
      "Comisaría 10",
      "Comisaría 11",
      "Comisaría 12",
      "Comisaría 13",
      "Comisaría 14",
      "Comisaría 15",
    ]);

    fireEvent.change(jefatura, { target: { value: "U.R. Norte" } });
    expect(opcionesDe(dependencia)).toEqual([
      ...DEPENDENCIAS_POR_REGIONAL["U.R. Norte"],
    ]);
    expect(opcionesDe(dependencia)).toEqual([
      "Cria. Yerba Buena",
      "Cria. Marti Coll",
      "Comisaría Cevil Redondo",
      "Comisaría El Corte",
      "Cria. Tafí Viejo",
      "Cria. Lomas de Tafí",
      "Comisaría Villa Obrera",
      "Comisaría El Colmenar",
      "Comisaría Los Pocitos",
      "Cria. Trancas",
      "Cria. Villa Mariano Moreno",
    ]);
  });

  it("recalcula y resetea Dependencia al cambiar de jefatura", () => {
    renderFormulario();
    const jefatura = screen.getByLabelText(/jefatura regional/i);
    const dependencia = screen.getByLabelText(/dependencia/i) as HTMLSelectElement;

    fireEvent.change(jefatura, { target: { value: "U.R. Norte" } });
    fireEvent.change(dependencia, { target: { value: "Cria. Yerba Buena" } });
    expect(dependencia.value).toBe("Cria. Yerba Buena");

    fireEvent.change(jefatura, { target: { value: "U.R. Sur" } });

    expect(dependencia.value).toBe("");
    expect(opcionesDe(dependencia)).toEqual([
      ...DEPENDENCIAS_POR_REGIONAL["U.R. Sur"],
    ]);
  });

  it("preserva un valor legacy fuera del catálogo al editar", () => {
    renderFormulario({ ...FORM_INICIAL, jefatura_regional: "asd", dependencia: "UNR" });
    const jefatura = screen.getByLabelText(/jefatura regional/i) as HTMLSelectElement;
    const dependencia = screen.getByLabelText(/dependencia/i) as HTMLSelectElement;

    expect(jefatura.value).toBe("asd");
    expect(dependencia).toBeEnabled();
    expect(dependencia.value).toBe("UNR");
  });

  it("entrega jefatura y dependencia elegidas en el submit", () => {
    const { onSubmit } = renderFormulario();
    fireEvent.change(screen.getByLabelText(/jefatura regional/i), {
      target: { value: "U.R. Sur" },
    });
    fireEvent.change(screen.getByLabelText(/dependencia/i), {
      target: { value: "Cria. Aguilares" },
    });

    fireEvent.click(screen.getByRole("button", { name: /guardar reporte/i }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      jefatura_regional: "U.R. Sur",
      dependencia: "Cria. Aguilares",
    });
  });

  it("envía jefatura, dependencia y horas tal cual se eligieron/escribieron", () => {
    const { onSubmit } = renderFormulario();

    fireEvent.change(screen.getByLabelText(/jefatura regional/i), {
      target: { value: "U.R. Norte" },
    });
    fireEvent.change(screen.getByLabelText(/dependencia/i), {
      target: { value: "Cria. Yerba Buena" },
    });
    const horaConsulta = screen.getByLabelText(/hora de consulta/i);
    const horaRespuesta = screen.getByLabelText(/hora de respuesta/i);
    fireEvent.change(horaConsulta, { target: { value: "14:30" } });
    fireEvent.change(horaRespuesta, { target: { value: "15:45" } });

    expect(horaConsulta).toHaveAttribute("type", "time");
    expect(horaRespuesta).toHaveAttribute("type", "time");

    fireEvent.click(screen.getByRole("button", { name: /guardar reporte/i }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      jefatura_regional: "U.R. Norte",
      dependencia: "Cria. Yerba Buena",
      hora_consulta: "14:30",
      hora_respuesta: "15:45",
    });
  });
});
