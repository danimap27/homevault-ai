"use client";

import { useEffect, useState } from "react";

/**
 * Botón que alterna el modo oscuro. Persiste la elección en localStorage
 * ("tema": "light" | "dark"); sin elección guardada se sigue al sistema.
 */
export function BotonTema() {
  const [oscuro, setOscuro] = useState<boolean>(false);

  useEffect(() => {
    setOscuro(document.documentElement.classList.contains("dark"));
  }, []);

  const alternar = () => {
    const siguiente = !oscuro;
    setOscuro(siguiente);
    document.documentElement.classList.toggle("dark", siguiente);
    try {
      localStorage.setItem("tema", siguiente ? "dark" : "light");
    } catch {
      // localStorage no disponible (modo privado): solo se aplica la clase.
    }
  };

  return (
    <button
      type="button"
      onClick={alternar}
      aria-label={oscuro ? "Activar modo claro" : "Activar modo oscuro"}
      className="boton-secundario"
    >
      {oscuro ? (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="size-5" aria-hidden>
          <path strokeLinecap="round" d="M12 3v2m0 14v2M5.6 5.6l1.4 1.4m10 10 1.4 1.4M3 12h2m14 0h2M5.6 18.4 7 17m10-10 1.4-1.4" />
          <circle cx={12} cy={12} r={4} />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="size-5" aria-hidden>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z" />
        </svg>
      )}
    </button>
  );
}
