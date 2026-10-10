import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("../../supabaseClient", () => ({ supabase: { from: vi.fn(() => ({ insert: vi.fn() })) } }));
vi.mock("../../data/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../data/api")>()),
  recolectarTodas: vi.fn(async () => []),
}));

import { InformeImpresion } from "./InformeImpresion";
import { FiltersProvider } from "../../state/FiltersContext";

function abrir(): { onClose: () => void } {
  const onClose = vi.fn();
  render(
    <FiltersProvider>
      <InformeImpresion onClose={onClose} />
    </FiltersProvider>,
  );
  return { onClose };
}

describe("InformeImpresion", () => {
  beforeEach(() => {
    window.print = vi.fn();
  });

  it("permite elegir fechas y gráficos, y los quita del informe al desmarcar", async () => {
    abrir();
    expect(screen.getByLabelText("Desde")).toBeInTheDocument();
    expect(screen.getByLabelText("Hasta")).toBeInTheDocument();

    const evolucion = screen.getByLabelText("Evolución diaria");
    expect(evolucion).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Ninguno" }));
    expect(evolucion).not.toBeChecked();

    await waitFor(() =>
      expect(screen.getByText(/Elegí al menos un gráfico/)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /Imprimir \/ Guardar PDF/ })).toBeDisabled();
  });

  it("imprime cuando hay datos cargados y al menos un gráfico", async () => {
    abrir();
    fireEvent.click(screen.getByRole("button", { name: "Ninguno" }));
    fireEvent.click(screen.getByLabelText("Totales (tarjetas KPI)"));
    const buscar = (): HTMLElement =>
      screen.getByRole("button", { name: /Imprimir \/ Guardar PDF/ });
    await waitFor(() => expect(buscar()).toBeEnabled());
    fireEvent.click(buscar());
    expect(window.print).toHaveBeenCalled();
  });

  it("no deja imprimir con un rango inválido y cierra con Escape", () => {
    const { onClose } = abrir();
    fireEvent.change(screen.getByLabelText("Desde"), { target: { value: "2999-01-01" } });
    expect(screen.getByRole("alert")).toHaveTextContent(/rango válido/);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
