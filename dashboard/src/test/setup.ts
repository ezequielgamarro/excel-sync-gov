import "@testing-library/jest-dom/vitest";

// Recharts usa `ResizeObserver` (no implementado por jsdom) al montar
// `ResponsiveContainer`. El stub permite renderizar los componentes sin romper
// el entorno de test; la tabla accesible y el DOM del panel se renderizan igual.
if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}
