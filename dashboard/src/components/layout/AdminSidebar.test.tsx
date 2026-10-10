/**
 * Sidebar responsivo: en escritorio es una columna fija; por debajo de `lg`
 * funciona como drawer off-canvas con overlay, cierre con Escape y estado
 * accesible (`aria-hidden` / `aria-current`).
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AdminSidebar } from "./AdminSidebar";

function matchMediaStub(matches: boolean): (query: string) => MediaQueryList {
  return ((query: string) => ({
    matches,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as (query: string) => MediaQueryList;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AdminSidebar responsivo", () => {
  it("en escritorio permanece visible aunque el drawer esté cerrado", () => {
    vi.stubGlobal("matchMedia", matchMediaStub(true));
    render(<AdminSidebar activeTab="resumen" onSelect={() => {}} open={false} />);

    const aside = document.getElementById("admin-sidebar");
    expect(aside).toHaveAttribute("aria-hidden", "false");
    expect(screen.queryByTestId("sidebar-overlay")).toBeNull();
  });

  it("en móvil cerrado: off-canvas, sin overlay y sin foco de menú", () => {
    vi.stubGlobal("matchMedia", matchMediaStub(false));
    render(
      <AdminSidebar activeTab="resumen" onSelect={() => {}} open={false} onClose={() => {}} />,
    );

    expect(document.getElementById("admin-sidebar")).toHaveAttribute("aria-hidden", "true");
    expect(screen.queryByTestId("sidebar-overlay")).toBeNull();
  });

  it("en móvil abierto: muestra overlay y cierra con Escape o clic en overlay", () => {
    vi.stubGlobal("matchMedia", matchMediaStub(false));
    const onClose = vi.fn();
    render(<AdminSidebar activeTab="resumen" onSelect={() => {}} open onClose={onClose} />);

    expect(document.getElementById("admin-sidebar")).toHaveAttribute("aria-hidden", "false");
    fireEvent.click(screen.getByTestId("sidebar-overlay"));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);

    fireEvent.keyDown(window, { key: "a" });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("marca la sección activa con aria-current", () => {
    vi.stubGlobal("matchMedia", matchMediaStub(true));
    render(<AdminSidebar activeTab="comparativas" onSelect={() => {}} />);

    expect(screen.getByRole("button", { name: /estadística total cisop/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
