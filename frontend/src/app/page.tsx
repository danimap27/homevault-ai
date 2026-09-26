"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Sparkles } from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import type { ResumenInteligencia } from "@/lib/types";
import { Cargando, ErrorWidget } from "@/components/estado-async";
import { WidgetCaducidades } from "@/components/dashboard/widget-caducidades";
import { WidgetTareasHoy } from "@/components/dashboard/widget-tareas-hoy";
import { WidgetFinanzas } from "@/components/dashboard/widget-finanzas";
import { WidgetReposicion } from "@/components/dashboard/widget-reposicion";
import { WidgetResumenHogar } from "@/components/dashboard/widget-resumen-hogar";
import { WidgetTareasStats } from "@/components/dashboard/widget-tareas-stats";

export default function Dashboard() {
  const [insights, setInsights] = useState<ResumenInteligencia | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getInsights()
      .then(setInsights)
      .catch((err) =>
        setError(
          err instanceof ErrorApi
            ? `Error ${err.status}: ${err.message}`
            : "API no disponible",
        ),
      );
  }, []);

  return (
    <div className="space-y-6">
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="tarjeta-bento-premium sm:col-span-2">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <div className="flex size-11 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-400">
                <Sparkles className="size-6" />
              </div>
              <div>
                <h2 className="text-lg font-semibold tracking-tight">
                  Bienvenido a HomeVault AI
                </h2>
                <p className="text-sm text-slate-400">
                  Inventario, tareas y despensa bajo control.
                </p>
              </div>
            </div>
            <Link
              href="/asistente"
              className="boton-primario justify-center sm:shrink-0"
            >
              <Sparkles className="size-4" /> Pregunta a tu casa
            </Link>
          </div>
        </div>

        <WidgetReposicion sugerencias={insights?.reposicion ?? []} />

        <WidgetCaducidades />
        <WidgetTareasHoy />

        {error && (
          <div className="sm:col-span-2">
            <ErrorWidget mensaje={`Inteligencia no disponible: ${error}`} />
          </div>
        )}
        {!error && insights === null && (
          <div className="tarjeta-bento sm:col-span-2">
            <Cargando />
          </div>
        )}
        {insights !== null && (
          <>
            <WidgetTareasStats stats={insights.tareas} />
            <WidgetResumenHogar datos={insights} />
          </>
        )}

        <WidgetFinanzas />
      </section>
    </div>
  );
}
