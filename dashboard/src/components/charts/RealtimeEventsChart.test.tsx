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
        { ts: "10:00", value: 10 },
        { ts: "11:00", value: 14 },
      ],
    });
    expect(screen.getByTestId("chart-realtime")).toBeInTheDocument();
  });

  it("ignora puntos sin etiqueta horaria y muestra vacío si no queda ninguno", () => {
    renderChart({ series: [{ ts: "", value: 5 }] });
    expect(screen.getByRole("status")).toHaveTextContent("SIN DATOS");
  });

  it("sin series muestra estado vacío (no sintético)", () => {
    renderChart({});
    expect(screen.getByRole("status")).toHaveTextContent("SIN DATOS");
  });

  it("no trae filtros propios (los globales viven en la cabecera)", () => {
    renderChart({ series: [{ ts: "10:00", value: 3 }] });
    expect(screen.queryByLabelText(/turno/i)).toBeNull();
    expect(screen.queryByLabelText(/unidad regional/i)).toBeNull();
    expect(screen.queryByLabelText(/rango/i)).toBeNull();
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
