import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Paleta neutra cálida legacy, se mantiene para no romper imports.
        arena: {
          50: "#faf9f7",
          100: "#f3f1ec",
          200: "#e5e1d8",
        },
        carbon: {
          800: "#1d1f24",
          900: "#14161a",
          950: "#0e1013",
        },
      },
      borderRadius: {
        bento: "1.25rem",
      },
      fontFamily: {
        sans: [
          "var(--font-geist-sans)",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      boxShadow: {
        glow: "0 0 20px rgba(16, 185, 129, 0.15)",
        "glow-violet": "0 0 20px rgba(139, 92, 246, 0.15)",
        "glow-amber": "0 0 20px rgba(245, 158, 11, 0.15)",
      },
    },
  },
  plugins: [],
};

export default config;
