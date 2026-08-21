"use client";

import { useEffect, useState } from "react";
import { Wallet } from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import type { ResumenFinanciero } from "@/lib/types";
import { formatoEuros, mesActual } from "@/lib/utils";
import { Cargando, ErrorWidget } from "@/components/estado-async";

export function WidgetFinanzas() {
  const [resumen, setResumen] = useState<ResumenFinanciero | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const mes = mesActual();
    api
      .getResumenFinanciero(mes)
      .then(setResumen)
      .catch((err) => {
        if (err instanceof ErrorApi && err.status === 404) {
          setResumen({ mes, total: 0, por_categoria: [] });
        } else {
          setError(
            err instanceof ErrorApi
              ? `Error ${err.status}: ${err.message}`
              : "API no disponible",
          );
        }
      });
  }, []);

  const topCategorias = (resumen?.por_categoria ?? [])
    .slice()
    .sort((a, b) => b.total - a.total)
    .slice(0, 4);

  return (
    <section aria-labelledby="titulo-finanzas" className="tarjeta-bento">
      <div className="mb-4 flex items-center gap-2">
        <div className="flex size-8 items-center justify-center rounded-lg bg-amber-500/15 text-amber-400">
          <Wallet className="size-4" />
        </div>
        <h2 id="titulo-finanzas" className="text-base font-semibold">
          Gastos del mes
        </h2>
      </div>
      {error && <ErrorWidget mensaje={error} />}
      {!error && resumen === null && <Cargando />}
      {resumen !== null && (
        <>
          <p className="text-3xl font-bold tracking-tight text-slate-100">
            {formatoEuros(resumen.total)}
          </p>
          <p className="mb-4 text-xs text-slate-500">
            Total de {resumen.mes}
          </p>
          {topCategorias.length > 0 && (
            <ul className="space-y-2 text-sm">
              {topCategorias.map((cat) => {
                const pct =
                  resumen.total > 0
                    ? Math.round((cat.total / resumen.total) * 100)
                    : 0;
                return (
                  <li key={cat.categoria}>
                    <div className="flex justify-between text-slate-300">
                      <span className="capitalize">{cat.categoria}</span>
                      <span className="font-medium">
                        {formatoEuros(cat.total)}
                      </span>
                    </div>
                    <div className="mt-1.5 h-1.5 rounded-full bg-slate-800">
                      <div
                        className="h-1.5 rounded-full bg-emerald-500 transition-all duration-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
