"use client";

import { useState } from "react";
import { Check, Plus, ShoppingBasket } from "lucide-react";
import { api } from "@/lib/api";
import type { SugerenciaReposicion, UrgenciaReposicion } from "@/lib/types";

const ESTILO_URGENCIA: Record<UrgenciaReposicion, string> = {
  critica: "border-rose-500/25 bg-rose-500/10 text-rose-200",
  alta: "border-amber-500/25 bg-amber-500/10 text-amber-200",
  media: "border-sky-500/25 bg-sky-500/10 text-sky-200",
};

const ETIQUETA_URGENCIA: Record<UrgenciaReposicion, string> = {
  critica: "Crítico",
  alta: "Alta",
  media: "Media",
};

/**
 * «Reponer pronto»: sugerencias de reposición priorizadas por urgencia,
 * con botón para añadirlas a la lista de la compra en un toque.
 */
export function WidgetReposicion({
  sugerencias,
}: {
  sugerencias: SugerenciaReposicion[];
}) {
  const [anadidos, setAnadidos] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  const anadir = async (s: SugerenciaReposicion) => {
    try {
      await api.anadirAListaCompra(
        s.nombre,
        undefined,
        s.unidad,
        s.categoria,
      );
      setAnadidos((prev) => ({ ...prev, [s.item_id]: true }));
      setError(null);
    } catch {
      setError(`No se pudo añadir ${s.nombre} a la compra`);
    }
  };

  const visibles = sugerencias.slice(0, 6);

  return (
    <section aria-labelledby="titulo-reposicion" className="tarjeta-bento sm:col-span-2">
      <div className="mb-4 flex items-center gap-2">
        <div className="flex size-9 items-center justify-center rounded-xl bg-amber-500/15 text-amber-400">
          <ShoppingBasket className="size-5" />
        </div>
        <div>
          <h2 id="titulo-reposicion" className="text-base font-semibold">
            Reponer pronto
          </h2>
          <p className="text-xs text-slate-500">
            {sugerencias.length === 0
              ? "Todo cubierto según tu ritmo de consumo."
              : `${sugerencias.length} ${sugerencias.length === 1 ? "producto" : "productos"} a vigilar`}
          </p>
        </div>
      </div>

      {error && <p className="mb-3 text-sm text-rose-300">{error}</p>}

      {visibles.length === 0 && (
        <p className="text-sm text-slate-500">
          Nada urgente. Las predicciones mejoran conforme registres consumos.
        </p>
      )}

      <ul className="grid gap-2 sm:grid-cols-2">
        {visibles.map((s) => {
          const enLista = s.ya_en_lista || anadidos[s.item_id];
          return (
            <li
              key={s.item_id}
              className={`flex items-center justify-between gap-2 rounded-xl border p-3 ${ESTILO_URGENCIA[s.urgencia]}`}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{s.nombre}</p>
                <p className="truncate text-xs opacity-80">
                  {ETIQUETA_URGENCIA[s.urgencia]} · {s.motivo}
                </p>
              </div>
              {enLista ? (
                <span className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-emerald-500/15 px-2 py-1 text-xs font-medium text-emerald-300">
                  <Check className="size-3.5" /> En lista
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => anadir(s)}
                  className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-slate-900/50 px-2 py-1 text-xs font-medium transition-colors hover:bg-slate-900/80"
                  aria-label={`Añadir ${s.nombre} a la lista de la compra`}
                >
                  <Plus className="size-3.5" /> Compra
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
