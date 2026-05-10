import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        civic: {
          ink: "#18212f",
          muted: "#667085",
          line: "#d8dee6",
          panel: "#ffffff",
          surface: "#f5f7f4",
          teal: "#117c78",
          blue: "#285b9f",
          amber: "#b76d1d"
        }
      },
      boxShadow: {
        panel: "0 1px 2px rgba(16, 24, 40, 0.08)"
      }
    }
  },
  plugins: []
};

export default config;
