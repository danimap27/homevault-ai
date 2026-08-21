import type { Config } from "tailwindcss";

// Modo oscuro por clase: el script inline de layout.tsx aplica la clase
// "dark" según preferencia guardada o prefers-color-scheme del sistema.
const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Paleta neutra cálida para el estilo Bento
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
    },
  },
  plugins: [],
};

export default config;
