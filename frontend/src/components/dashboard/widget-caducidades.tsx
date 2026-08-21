"use client";

import { useEffect, useState } from "react";
import { api, ErrorApi } from "@/lib/api";
import type { ItemCaducidad } from "@/lib/types";
import { Cargando, ErrorWidget } from "@/components/estado-async";

type NivelSemaforo = "rojo" | "amarillo" | "verde";

/**
 * Semáforo de caducidades: rojo <24h (dias_restantes <= 0),
 * amarillo <72h (1-2 días), verde 3-5 días.
 */
function nivelDe(diasRestantes: number): NivelSemaforo {
  if (diasRestantes <= 0) return "rojo";
  if (diasRestantes <= 2) return "amarillo";
  return "verde";
}

const ESTILOS_NIVEL: Record<NivelSemaforo, string> = {
  rojo: "border-red-300 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950/60 dark:text-red-300",
  amarillo:
    "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-300",
  verde:
    "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-300",
};

const ETIQUETA_DIAS: Record<NivelSemaforo, string> = {
  rojo: "< 24 h",
  amarillo: "< 72 h",
  verde: "3-5 días",
};

export function WidgetCaducidades() {
  const [items, setItems] = useState<ItemCaducidad[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getCaducidades(5)
      .then(setItems)
      .catch((err) =>
        setError(
          err instanceof ErrorApi
            ? `Error ${err.status}: ${err.message}`
            : "API no disponible",
        ),
      );
  }, []);

  const porNivel = (nivel: NivelSemaforo) =>
    (items ?? []).filter((i) => nivelDe(i.dias_restantes) === nivel);

  return (
    <section aria-labelledby="titulo-caducidades" className="tarjeta-bento sm:col-span-2">
      <h2 id="titulo-caducidades" className="mb-3 text-base font-semibold">
        Semáforo de caducidades
      </h2>
      {error && <ErrorWidget mensaje={error} />}
      {!error && items === null && <Cargando />}
      {items !== null && items.length === 0 && (
        <p className="text-sm text-carbon-950/60 dark:text-arena-100/60">
          Nada caduca en los próximos 5 días.
        </p>
      )}
      {items !== null && items.length > 0 && (
        <ul className="grid gap-2 sm:grid-cols-3">
          {(["rojo", "amarillo", "verde"] as const).map((nivel) => {
            const grupo = porNivel(nivel);
            return (
              <li
                key={nivel}
                className={`rounded-xl border p-3 ${ESTILOS_NIVEL[nivel]}`}
              >
                <p className="mb-1 text-xs font-bold uppercase tracking-wide">
                  {ETIQUETA_DIAS[nivel]} · {grupo.length}
                </p>
                <ul className="space-y-1 text-sm">
                  {grupo.slice(0, 4).map((item) => (
                    <li key={`${item.item_id}-${item.origen}`} className="truncate">
                      {item.nombre}
                      <span className="opacity-70">
                        {" "}({item.dias_restantes <= 0 ? "hoy/ayer" : `${item.dias_restantes} d`})
                      </span>
                    </li>
                  ))}
                  {grupo.length === 0 && (
                    <li className="opacity-60">Sin ítems</li>
                  )}
                  {grupo.length > 4 && (
                    <li className="opacity-70">+{grupo.length - 4} más</li>
                  )}
                </ul>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
