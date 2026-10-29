/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "../../packages/ui/src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        display: ["Orbitron", "Inter", "ui-sans-serif", "sans-serif"],
      },
      colors: {
        surface: {
          deep: "#0f172a",
          graphite: "#1e293b",
          panel: "#334155",
        },
        light: "#f8fafc",
        error: "#f87171",
        ok: "#4ade80",
        warn: "#fbbf24",
        idle: "#94a3b8",
        accent: {
          // CSS-variable driven so the HUD accent rethemes at runtime
          // (Settings → Appearance). Defaults in index.css :root match
          // the original palette.
          cyan: "rgb(var(--accent) / <alpha-value>)",
          blue: "rgb(var(--accent-2) / <alpha-value>)",
        },
        status: {
          ok: "#4ade80",
          warn: "#fbbf24",
          error: "#f87171",
          idle: "#94a3b8",
        },
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "orb-breath": "orb-breath 4s ease-in-out infinite",
        "orb-listen": "orb-listen 2s ease-in-out infinite",
        "spin-slow": "spin 8s linear infinite",
      },
      keyframes: {
        "orb-breath": {
          "0%, 100%": { transform: "scale(1)", opacity: "0.6" },
          "50%": { transform: "scale(1.15)", opacity: "0.9" },
        },
        "orb-listen": {
          "0%, 100%": {
            transform: "scale(1)",
            boxShadow: "0 0 20px rgb(var(--accent) / 0.4)",
          },
          "50%": {
            transform: "scale(1.1)",
            boxShadow: "0 0 40px rgb(var(--accent) / 0.8)",
          },
        },
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.5rem",
      },
    },
  },
  plugins: [],
};
