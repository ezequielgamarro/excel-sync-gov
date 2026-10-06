import { describe, expect, it } from "vitest";
import {
  formatAge,
  formatInteger,
  formatSignedInteger,
  formatSignedPercent,
  formatVariation,
} from "./format";

describe("formato es-CL (RNF-15.a/b)", () => {
  it("formatea enteros con separador de miles por punto", () => {
    expect(formatInteger(184732)).toBe("184.732");
    expect(formatInteger(0)).toBe("0");
  });

  it("usa signo explícito y menos tipográfico", () => {
    expect(formatSignedInteger(3120)).toBe("+3.120");
    expect(formatSignedInteger(-412)).toBe("−412");
    expect(formatSignedInteger(0)).toBe("0");
  });

  it("formatea porcentajes con 1 decimal y coma decimal", () => {
    expect(formatSignedPercent(1.71)).toBe("+1,7 %");
    expect(formatSignedPercent(-13.95)).toBe("−14,0 %");
    expect(formatSignedPercent(0)).toBe("0,0 %");
  });

  it("compone la variación con glifo + signo + porcentaje", () => {
    expect(formatVariation(12, 3.4)?.text).toBe("▲ +12 (+3,4 %)");
    expect(formatVariation(-5, -1.1)?.text).toBe("▼ −5 (−1,1 %)");
    expect(formatVariation(0, 0)?.text).toBe("= 0 (0,0 %)");
    expect(formatVariation(null, null)).toBeNull();
  });

  it("formatea la edad de frescura", () => {
    expect(formatAge(45)).toBe("45s");
    expect(formatAge(121)).toBe("2m");
    expect(formatAge(7200)).toBe("2h");
  });
});
