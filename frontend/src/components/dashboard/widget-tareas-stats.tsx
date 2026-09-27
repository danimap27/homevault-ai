"use client";

import { CalendarClock, CheckCircle2, Flame, Users } from "lucide-react";
import type { EstadisticasTareas } from "@/lib/types";

const COLORES_CUOTA = [
  "bg-emerald-500",
  "bg-sky-500",
  "bg-violet-500",
  "bg-amber-500",
  "bg-rose-500",
];

/**
 * Estadísticas del tablero de tareas: carga pendiente, equidad entre
 * convivientes y puntualidad de los últimos 30 días.
 */
export function WidgetTareasStats({
  stats,
}: {
  stats: EstadisticasTareas;
}) {
  const cumplimiento =
    stats.completadas_30d > 0 && stats.a_tiempo_30d !== null
      ? Math.round((100 * stats.a_tiempo_30d) / stats.completadas_30d)
      : null;

  return (
    <section aria-labelledby="titulo-tareas-stats" className="tarjeta-bento sm:col-span-2">
      <div className="mb-4 flex items-center gap-2">
        <div className="flex size-9 items-center justify-center rounded-xl bg-sky-500/15 text-sky-400">
          <Users className="size-5" />
        </div>
        <div>
          <h2 id="titulo-tareas-stats" className="text-base font-semibold">
            Equipo de casa
          </h2>
          <p className="text-xs text-slate-500">
            Reparto de tareas y estado del mes
          </p>
        </div>
      </div>

      <div className="mb-4 grid grid-cols-3 gap-2">
        <div className="rounded-xl border border-slate-700/30 bg-slate-900/40 p-3 text-center">
          <CheckCircle2 className="mx-auto mb-1 size-4 text-emerald-400" />
          <p className="text-lg font-semibold tabular-nums">{stats.completadas_mes}</p>
          <p className="text-xs text-slate-500">hechas este mes</p>
        </div>
        <div className="rounded-xl border border-slate-700/30 bg-slate-900/40 p-3 text-center">
          <CalendarClock className="mx-auto mb-1 size-4 text-sky-400" />
          <p className="text-lg font-semibold tabular-nums">{stats.proximas_7_dias}</p>
          <p className="text-xs text-slate-500">próximos 7 días</p>
        </div>
        <div
          className={`rounded-xl border p-3 text-center ${
            stats.vencidas > 0
              ? "border-rose-500/25 bg-rose-500/10"
              : "border-slate-700/30 bg-slate-900/40"
          }`}
        >
          <Flame
            className={`mx-auto mb-1 size-4 ${
              stats.vencidas > 0 ? "text-rose-400" : "text-slate-400"
            }`}
          />
          <p
            className={`text-lg font-semibold tabular-nums ${
              stats.vencidas > 0 ? "text-rose-200" : ""
            }`}
          >
            {stats.vencidas}
          </p>
          <p className="text-xs text-slate-500">vencidas</p>
        </div>
      </div>

      {stats.por_conviviente.length > 0 ? (
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            Equidad del mes
          </p>
          <ul className="space-y-2">
            {stats.por_conviviente.map((cuota, indice) => (
              <li key={cuota.nombre} className="flex items-center gap-3">
                <span className="w-24 shrink-0 truncate text-sm text-slate-300">
                  {cuota.nombre}
                </span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-800">
                  <div
                    className={`h-full rounded-full ${COLORES_CUOTA[indice % COLORES_CUOTA.length]}`}
                    style={{ width: `${Math.min(100, Math.max(4, cuota.porcentaje))}%` }}
                  />
                </div>
                <span className="w-24 shrink-0 text-right text-xs tabular-nums text-slate-400">
                  {cuota.completadas} ({cuota.porcentaje} %)
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-sm text-slate-500">
          Aún no hay tareas completadas este mes.
        </p>
      )}

      {cumplimiento !== null && (
        <p className="mt-3 text-xs text-slate-500">
          Puntualidad (30 días): {cumplimiento} % de{" "}
          {stats.completadas_30d} tareas hechas a tiempo.
        </p>
      )}

      {stats.top_vencidas.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            Más retrasadas
          </p>
          <ul className="space-y-1 text-sm">
            {stats.top_vencidas.slice(0, 3).map((v) => (
              <li key={v.task_id} className="flex min-w-0 items-center justify-between gap-2 text-slate-300">
                <span className="min-w-0 truncate">{v.titulo}</span>
                <span className="shrink-0 text-xs text-rose-300">
                  {v.dias_retraso} d de retraso
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
