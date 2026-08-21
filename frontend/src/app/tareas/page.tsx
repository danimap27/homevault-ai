"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ErrorApi } from "@/lib/api";
import type { Tarea } from "@/lib/types";
import { quienLeToca } from "@/components/dashboard/widget-tareas-hoy";
import { Cargando, ErrorWidget } from "@/components/estado-async";

const ESTILO_PRIORIDAD: Record<Tarea["prioridad"], string> = {
  baja: "bg-arena-100 text-carbon-800 dark:bg-carbon-800 dark:text-arena-100",
  media: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  alta: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  urgente: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};

/**
 * Tablero de tareas: columna de pendientes (con indicador de bloqueo por
 * falta de recambio) y columna de completadas. Las completadas usan la ruta
 * del spec GET /api/tasks?estado=completada (PENDIENTE en el backend).
 */
export default function TareasPage() {
  const [pendientes, setPendientes] = useState<Tarea[] | null>(null);
  const [completadas, setCompletadas] = useState<Tarea[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const cargar = useCallback(() => {
    setError(null);
    api
      .getTareasPendientes()
      .then(setPendientes)
      .catch((err) =>
        setError(
          err instanceof ErrorApi
            ? `Error ${err.status}: ${err.message}`
            : "API no disponible",
        ),
      );
    // Endpoint del spec aún pendiente: si falla, se muestra la columna vacía.
    api
      .getTareasCompletadas()
      .then(setCompletadas)
      .catch(() => setCompletadas([]));
  }, []);

  useEffect(cargar, [cargar]);

  const completar = async (tarea: Tarea) => {
    try {
      await api.completarTarea(tarea.id);
      setAviso(`Tarea completada: ${tarea.titulo}`);
      cargar();
    } catch (err) {
      setAviso(
        err instanceof ErrorApi ? err.message : "No se pudo completar la tarea",
      );
    }
  };

  const verificarStock = async (tarea: Tarea) => {
    try {
      const actualizada = await api.verificarStockTarea(tarea.id);
      setAviso(
        actualizada.bloqueada_por_stock
          ? `Falta recambio para: ${tarea.titulo}`
          : `Stock OK para: ${tarea.titulo}`,
      );
      cargar();
    } catch (err) {
      setAviso(
        err instanceof ErrorApi ? err.message : "No se pudo verificar el stock",
      );
    }
  };

  return (
    <div>
      {aviso && (
        <p
          className="mb-3 rounded-xl border border-emerald-300 bg-emerald-50 p-2.5 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-300"
          role="status"
        >
          {aviso}
        </p>
      )}
      {error && <ErrorWidget mensaje={error} />}
      {!error && pendientes === null && <Cargando />}

      {pendientes !== null && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <section aria-labelledby="titulo-pendientes">
            <h2 id="titulo-pendientes" className="mb-3 text-base font-semibold">
              Pendientes ({pendientes.length})
            </h2>
            <ul className="space-y-3">
              {pendientes.length === 0 && (
                <li className="tarjeta-bento text-sm text-carbon-950/60 dark:text-arena-100/60">
                  Todo hecho. Buen trabajo.
                </li>
              )}
              {pendientes.map((tarea) => (
                <li key={tarea.id} className="tarjeta-bento">
                  <div className="mb-2 flex items-start justify-between gap-2">
                    <h3 className="min-w-0 font-semibold leading-tight">
                      {tarea.titulo}
                    </h3>
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${ESTILO_PRIORIDAD[tarea.prioridad]}`}
                    >
                      {tarea.prioridad}
                    </span>
                  </div>
                  <div className="mb-3 flex flex-wrap gap-1.5 text-xs">
                    {tarea.zona && (
                      <span className="rounded-full bg-arena-100 px-2 py-0.5 dark:bg-carbon-800">
                        {tarea.zona}
                      </span>
                    )}
                    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                      Le toca a {quienLeToca(tarea)}
                    </span>
                    {tarea.fecha_programada && (
                      <span className="rounded-full bg-arena-100 px-2 py-0.5 dark:bg-carbon-800">
                        {tarea.fecha_programada}
                      </span>
                    )}
                    {tarea.bloqueada_por_stock && (
                      <span
                        className="rounded-full bg-red-100 px-2 py-0.5 font-medium text-red-800 dark:bg-red-950 dark:text-red-300"
                        title="La tarea no puede hacerse: falta recambio en el inventario"
                      >
                        Bloqueada: falta recambio
                      </span>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => completar(tarea)}
                      className="boton-primario flex-1"
                    >
                      Completar
                    </button>
                    {tarea.consumibles_requeridos.length > 0 && (
                      <button
                        type="button"
                        onClick={() => verificarStock(tarea)}
                        className="boton-secundario"
                      >
                        Verificar stock
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="titulo-completadas">
            <h2 id="titulo-completadas" className="mb-3 text-base font-semibold">
              Completadas ({completadas.length})
            </h2>
            <ul className="space-y-2">
              {completadas.length === 0 && (
                <li className="tarjeta-bento text-sm text-carbon-950/60 dark:text-arena-100/60">
                  Sin completadas (o endpoint GET /api/tasks?estado=completada
                  pendiente en el backend).
                </li>
              )}
              {completadas.map((tarea) => (
                <li
                  key={tarea.id}
                  className="tarjeta-bento flex items-center justify-between gap-2 text-sm opacity-70"
                >
                  <span className="min-w-0 truncate line-through">
                    {tarea.titulo}
                  </span>
                  {tarea.ultima_realizacion && (
                    <span className="shrink-0 text-xs">
                      {tarea.ultima_realizacion.slice(0, 10)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}
