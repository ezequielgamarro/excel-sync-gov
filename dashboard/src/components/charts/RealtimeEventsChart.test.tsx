import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { FiltersProvider } from "../../state/FiltersContext";
import { RealtimeEventsChart } from "./RealtimeEventsChart";

function renderChart(props: React.ComponentProps<typeof RealtimeEventsChart>) {
  return render(
    <FiltersProvider>
      <RealtimeEventsChart {...props} />
    </FiltersProvider>,
  );
}

describe("RealtimeEventsChart — serie real y estados", () => {
  it("renderiza la serie real recibida por props", () => {
    renderChart({
      series: [
        { ts: "2026-10-06T10:00:00Z", value: 10 },
        { ts: "2026-10-06T11:00:00Z", value: 14 },
      ],
    });
    expect(screen.getByTestId("chart-realtime")).toBeInTheDocument();
  });

  it("ignora puntos con fecha inválida y muestra vacío si no queda ninguno", () => {
    renderChart({ series: [{ ts: "no-es-fecha", value: 5 }] });
    expect(screen.getByRole("status")).toHaveTextContent("SIN DATOS");
  });

  it("sin series muestra estado vacío (no sintético)", () => {
    renderChart({});
    expect(screen.getByRole("status")).toHaveTextContent("SIN DATOS");
  });

  it("no expone ningún selector de Turno (filtro eliminado)", () => {
    renderChart({ series: [{ ts: "2026-10-06T10:00:00Z", value: 3 }] });
    expect(screen.queryByLabelText(/turno/i)).toBeNull();
    expect(document.getElementById("filter-turno")).toBeNull();
    // Unidad Regional + Rango siguen presentes.
    expect(document.getElementById("filter-unidad")).not.toBeNull();
    expect(document.getElementById("filter-rango")).not.toBeNull();
  });

  it("muestra carga y error", () => {
    const { rerender } = renderChart({ loading: true });
    expect(screen.getByRole("status", { name: /Cargando/ })).toBeInTheDocument();

    rerender(
      <FiltersProvider>
        <RealtimeEventsChart error="caída" />
      </FiltersProvider>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("caída");
  });
});
