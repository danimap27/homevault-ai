"use client";

import { useEffect, useState } from "react";
import { api, ErrorApi } from "@/lib/api";
import type { ResumenFinanciero } from "@/lib/types";
import { formatoEuros, mesActual } from "@/lib/utils";
import { Cargando, ErrorWidget } from "@/components/estado-async";

/**
 * Widget de resumen financiero mensual a partir de los gastos del vault.
 * Consume GET /api/finance/summary?mes=YYYY-MM; si el mes aún no tiene
 * archivo de gastos (404) se muestra el total a cero.
 */
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
      <h2 id="titulo-finanzas" className="mb-3 text-base font-semibold">
        Gastos del mes
      </h2>
      {error && <ErrorWidget mensaje={error} />}
      {!error && resumen === null && <Cargando />}
      {resumen !== null && (
        <>
          <p className="text-3xl font-bold tracking-tight">
            {formatoEuros(resumen.total)}
          </p>
          <p className="mb-3 text-xs text-carbon-950/50 dark:text-arena-100/50">
            Total de {resumen.mes}
          </p>
          {topCategorias.length > 0 && (
            <ul className="space-y-1.5 text-sm">
              {topCategorias.map((cat) => {
                const pct =
                  resumen.total > 0
                    ? Math.round((cat.total / resumen.total) * 100)
                    : 0;
                return (
                  <li key={cat.categoria}>
                    <div className="flex justify-between">
                      <span className="capitalize">{cat.categoria}</span>
                      <span className="font-medium">
                        {formatoEuros(cat.total)}
                      </span>
                    </div>
                    <div className="mt-0.5 h-1.5 rounded-full bg-arena-200 dark:bg-carbon-800">
                      <div
                        className="h-1.5 rounded-full bg-emerald-500"
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
