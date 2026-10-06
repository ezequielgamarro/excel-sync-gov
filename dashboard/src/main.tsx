import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { CyberBackdrop } from "./components/CyberBackdrop";
import { ComparisonProvider } from "./state/ComparisonContext";
import { FiltersProvider } from "./state/FiltersContext";
import "./index.css";

// PWA (T47): registra el Service Worker de SOLO shell. En desarrollo se omite
// para no interferir con el HMR; en producción cachea únicamente el app shell.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`).catch(() => {
      /* el SW es opcional; nunca debe romper la app */
    });
  });
}

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(
    <StrictMode>
      <CyberBackdrop />
      <div className="app-layer">
        <ComparisonProvider>
          <FiltersProvider>
            <App />
          </FiltersProvider>
        </ComparisonProvider>
      </div>
    </StrictMode>,
  );
}
