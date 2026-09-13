import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        hud: {
          bg: "#05070f",
          panel: "#0b1220",
          accent: "#38bdf8",
          warn: "#f59e0b",
          danger: "#ef4444",
          ok: "#22c55e",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
