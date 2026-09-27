"use client";

import { Plus } from "lucide-react";

/**
 * Abre la barra de comandos (ingesta rápida: escribir o subir foto del
 * ticket). En escritorio equivale a Ctrl K; en móvil no hay teclado físico,
 * así que este botón es la vía de acceso.
 */
export function BotonComandos() {
  return (
    <button
      type="button"
      onClick={() => window.dispatchEvent(new CustomEvent("hv:comandos"))}
      aria-label="Añadir por texto o foto (Ctrl K)"
      title="Añadir por texto o foto (Ctrl K)"
      className="flex items-center gap-2 rounded-xl border border-slate-700/40 bg-slate-900/60 px-3 py-2 text-sm text-slate-300 transition-colors hover:border-emerald-500/40 hover:text-emerald-200"
    >
      <Plus className="size-4" />
      <span className="hidden sm:inline">Añadir</span>
    </button>
  );
}
