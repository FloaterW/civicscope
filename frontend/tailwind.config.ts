import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        civic: {
          ink: "var(--civic-ink)",
          muted: "var(--civic-muted)",
          line: "var(--civic-line)",
          panel: "var(--civic-panel)",
          surface: "var(--civic-surface)",
          teal: "var(--civic-teal)",
          blue: "var(--civic-blue)",
          amber: "var(--civic-amber)",
          subtle: "var(--civic-subtle)",
          hover: "var(--civic-hover)"
        }
      },
      boxShadow: {
        panel: "var(--shadow-panel)"
      },
      keyframes: {
        "skeleton-pulse": {
          "0%, 100%": { opacity: "0.4" },
          "50%": { opacity: "0.8" }
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" }
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(12px)" },
          to: { opacity: "1", transform: "translateY(0)" }
        }
      },
      animation: {
        "skeleton-pulse": "skeleton-pulse 1.5s ease-in-out infinite",
        "fade-in": "fade-in 0.25s ease-out",
        "slide-up": "slide-up 0.3s ease-out"
      }
    }
  },
  plugins: []
};

export default config;
