/** @type {import('tailwindcss').Config} */
// Paleta institucional policial (dark, bordes redondeados, azul neón). Los
// mismos hex existen como variables CSS en `src/styles/tokens.css` para usarse
// desde CSS puro, canvas y estilos de Recharts.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        night: "#04070F",
        surface: "#0A101C",
        surface2: "#111A2E",
        surface3: "#16223A",
        border: "#1E2C48",
        "border-strong": "#2C4069",
        ink: "#F2F6FC",
        ink2: "#C3CFE0",
        muted: "#8FA1BA",
        accent: "#4CC2FF",
        "accent-strong": "#1E90FF",
        "accent-bright": "#8FE3FF",
        pos: "#34D399",
        neg: "#F87171",
        warn: "#FBBF24",
        neutral: "#94A3B8",
      },
      fontFamily: {
        display: ['"Barlow Condensed"', '"Arial Narrow"', "system-ui", "sans-serif"],
        sans: ["Barlow", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      borderRadius: {
        panel: "18px",
        card: "18px",
        pill: "9999px",
      },
      boxShadow: {
        raise: "0 10px 30px -18px rgba(0, 0, 0, 0.9)",
        glow: "0 0 0 1px var(--accent-glow)",
      },
      spacing: {
        18: "4.5rem",
      },
    },
  },
  plugins: [],
};
