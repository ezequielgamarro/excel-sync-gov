import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const srcRoot = join(here, "..");
const dashboardRoot = join(here, "..", "..");

function listSourceFiles(root: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(root)) {
    const full = join(root, entry);
    if (statSync(full).isDirectory()) {
      listSourceFiles(full, acc);
    } else if (/\.(ts|tsx)$/.test(entry) && !/\.test\.(ts|tsx)$/.test(entry)) {
      acc.push(full);
    }
  }
  return acc;
}

describe("seguridad del frontend (T58, AM-06 / AM-10 / AM-11)", () => {
  it("no usa dangerouslySetInnerHTML ni innerHTML directo (escape-by-default)", () => {
    for (const file of listSourceFiles(srcRoot)) {
      const content = readFileSync(file, "utf8");
      expect(content, file).not.toContain("dangerouslySetInnerHTML");
      expect(content, file).not.toMatch(/\.innerHTML\s*=/);
    }
  });

  it("la CSP no permite unsafe-inline en script-src y bloquea framing", () => {
    const headers = readFileSync(join(dashboardRoot, "public", "_headers"), "utf8");
    expect(headers).toContain("frame-ancestors 'none'");
    expect(headers).toContain("X-Frame-Options: DENY");
    const scriptSrc = headers.match(/script-src([^;]*);/);
    expect(scriptSrc).not.toBeNull();
    expect(scriptSrc?.[1] ?? "").not.toContain("unsafe-inline");

    const html = readFileSync(join(dashboardRoot, "index.html"), "utf8");
    expect(html).toContain("script-src 'self'");
    expect(html).not.toMatch(/script-src[^;]*unsafe-inline/);
  });

  it("el Service Worker nunca cachea API ni WSS", () => {
    const sw = readFileSync(join(dashboardRoot, "public", "sw.js"), "utf8");
    expect(sw).toContain("/api/");
    expect(sw).toContain("/ws");
    expect(sw).toMatch(/wss?:/);
    // El shell cache solo incluye el app shell, no respuestas de datos.
    expect(sw).toContain("SHELL_CACHE");
    expect(sw).not.toMatch(/caches\.open\([^)]*\)\s*\.then\([^)]*fetch\([^)]*api/i);
  });
});
