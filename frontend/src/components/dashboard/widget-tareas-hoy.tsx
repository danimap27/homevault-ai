"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ErrorApi } from "@/lib/api";
import type { Tarea } from "@/lib/types";
import { hoyISO } from "@/lib/utils";
import { Cargando, ErrorWidget } from "@/components/estado-async";

/** Devuelve a quién le toca la tarea según el turno rotativo del vault. */
export function quienLeToca(tarea: Tarea): string {
  if (tarea.rotacion_convivientes.length > 0) {
    const idx = tarea.indice_rotacion_actual % tarea.rotacion_convivientes.length;
    return tarea.rotacion_convivientes[idx];
  }
  return tarea.asignado_a ?? "Sin asignar";
}

/**
 * Widget de tareas del día: pendientes programadas para hoy (o sin fecha),
 * mostrando a quién le toca según la rotación de convivientes.
 */
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
      <h2 id="titulo-tareas-hoy" className="mb-3 text-base font-semibold">
        Tareas del día
      </h2>
      {error && <ErrorWidget mensaje={error} />}
      {!error && tareas === null && <Cargando />}
      {tareas !== null && deHoy.length === 0 && (
        <p className="text-sm text-carbon-950/60 dark:text-arena-100/60">
          Nada pendiente para hoy.
        </p>
      )}
      {tareas !== null && deHoy.length > 0 && (
        <ul className="space-y-2">
          {deHoy.slice(0, 5).map((tarea) => (
            <li
              key={tarea.id}
              className="flex items-center justify-between gap-2 rounded-xl
                border border-arena-200 p-2.5 text-sm dark:border-carbon-800"
            >
              <span className="min-w-0 truncate">
                {tarea.titulo}
                {tarea.bloqueada_por_stock && (
                  <span
                    className="ml-1 text-amber-600 dark:text-amber-400"
                    title="Bloqueada por falta de recambio"
                  >
                    (sin recambio)
                  </span>
                )}
              </span>
              <span
                className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5
                  text-xs font-medium text-emerald-800
                  dark:bg-emerald-950 dark:text-emerald-300"
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
          className="mt-2 inline-block text-sm text-emerald-600 hover:underline dark:text-emerald-400"
        >
          Ver las {deHoy.length} tareas
        </Link>
      )}
    </section>
  );
}
