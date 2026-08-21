"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckSquare, ChevronRight } from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import type { Tarea } from "@/lib/types";
import { hoyISO } from "@/lib/utils";
import { Cargando, ErrorWidget } from "@/components/estado-async";

export function quienLeToca(tarea: Tarea): string {
  if (tarea.rotacion_convivientes.length > 0) {
    const idx = tarea.indice_rotacion_actual % tarea.rotacion_convivientes.length;
    return tarea.rotacion_convivientes[idx];
  }
  return tarea.asignado_a ?? "Sin asignar";
}

export function WidgetTareasHoy() {
  const [tareas, setTareas] = useState<Tarea[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getTareasPendientes()
      .then(setTareas)
      .catch((err) =>
        setError(
          err instanceof ErrorApi
            ? `Error ${err.status}: ${err.message}`
            : "API no disponible",
        ),
      );
  }, []);

  const hoy = hoyISO();
  const deHoy = (tareas ?? []).filter(
    (t) => t.fecha_programada === null || t.fecha_programada <= hoy,
  );

  return (
    <section aria-labelledby="titulo-tareas-hoy" className="tarjeta-bento">
      <div className="mb-4 flex items-center gap-2">
        <div className="flex size-8 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-400">
          <CheckSquare className="size-4" />
        </div>
        <h2 id="titulo-tareas-hoy" className="text-base font-semibold">
          Tareas del día
        </h2>
      </div>
      {error && <ErrorWidget mensaje={error} />}
      {!error && tareas === null && <Cargando />}
      {tareas !== null && deHoy.length === 0 && (
        <p className="text-sm text-slate-500">
          Nada pendiente para hoy.
        </p>
      )}
      {tareas !== null && deHoy.length > 0 && (
        <ul className="space-y-2">
          {deHoy.slice(0, 5).map((tarea) => (
            <li
              key={tarea.id}
              className="flex items-center justify-between gap-2 rounded-xl border border-slate-700/30 bg-slate-950/30 p-2.5 text-sm transition-colors hover:border-slate-600/50"
            >
              <span className="min-w-0 truncate">
                {tarea.titulo}
                {tarea.bloqueada_por_stock && (
                  <span
                    className="ml-1 text-amber-400"
                    title="Bloqueada por falta de recambio"
                  >
                    (sin recambio)
                  </span>
                )}
              </span>
              <span
                className="shrink-0 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-300"
                title="Turno rotativo"
              >
                {quienLeToca(tarea)}
              </span>
            </li>
          ))}
        </ul>
      )}
      {tareas !== null && deHoy.length > 5 && (
        <Link
          href="/tareas"
          className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-emerald-400 transition-colors hover:text-emerald-300"
        >
          Ver las {deHoy.length} tareas <ChevronRight className="size-4" />
        </Link>
      )}
    </section>
  );
}
