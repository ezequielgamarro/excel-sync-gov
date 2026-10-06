/**
 * T68 — Accesibilidad: contraste WCAG 2.2 AA con la paleta §11.2 (CA-02.8,
 * CA-05.3, RNF-09.b).
 *
 * Calcula el ratio de contraste real (fórmula WCAG) de las combinaciones
 * texto/fondo y de los objetos gráficos de la paleta fija. Complementa la
 * auditoría axe-core de `e2e/a11y.spec.ts`: aquí se verifica que los hex
 * declarados cumplen ≥ 4,5:1 (texto normal) y ≥ 3:1 (texto grande/objetos).
 */

import { describe, expect, it } from "vitest";

type Rgb = [number, number, number];

function hexToRgb(hex: string): Rgb {
  const value = hex.replace("#", "").trim();
  return [
    Number.parseInt(value.slice(0, 2), 16),
    Number.parseInt(value.slice(2, 4), 16),
    Number.parseInt(value.slice(4, 6), 16),
  ];
}

function channelToLinear(channel: number): number {
  const c = channel / 255;
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function luminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex);
  return 0.2126 * channelToLinear(r) + 0.7152 * channelToLinear(g) + 0.0722 * channelToLinear(b);
}

export function contrastRatio(foreground: string, background: string): number {
  const a = luminance(foreground);
  const b = luminance(background);
  const lighter = Math.max(a, b);
  const darker = Math.min(a, b);
  return (lighter + 0.05) / (darker + 0.05);
}

// Paleta institucional (tokens.css).
const BG = "#0a101c";
const BG_BASE = "#04070f";
const SURFACE_2 = "#111a2e";

const NORMAL_TEXT: Array<[string, string]> = [
  ["#f2f6fc", BG], // text-primary
  ["#c3cfe0", BG], // text-secondary
  ["#8fa1ba", BG], // text-muted
  ["#4cc2ff", BG], // accent (azul neón/eléctrico)
  ["#8fe3ff", BG], // accent-bright
  ["#34d399", BG], // pos
  ["#f87171", BG], // neg
  ["#fbbf24", BG], // warn
  ["#94a3b8", BG], // neutral
];

const GRAPHIC_OBJECTS: Array<[string, string]> = [
  ["#4cc2ff", BG],
  ["#1e90ff", SURFACE_2],
  ["#34d399", BG_BASE],
  ["#f87171", BG_BASE],
];

describe("contraste WCAG 2.2 AA de la paleta institucional (RNF-09.b)", () => {
  it.each(NORMAL_TEXT)("texto %s sobre %s cumple ≥ 4,5:1", (fg, bg) => {
    expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(GRAPHIC_OBJECTS)("objeto gráfico %s sobre %s cumple ≥ 3:1", (fg, bg) => {
    expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(3);
  });

  it("coincide con los valores de referencia de la paleta", () => {
    // #F2F6FC sobre #0A101C ≈ 17,5:1; #4CC2FF sobre #0A101C ≈ 9,5:1.
    expect(contrastRatio("#f2f6fc", "#0a101c")).toBeGreaterThanOrEqual(15);
    expect(contrastRatio("#4cc2ff", "#0a101c")).toBeGreaterThanOrEqual(8.5);
  });
});
