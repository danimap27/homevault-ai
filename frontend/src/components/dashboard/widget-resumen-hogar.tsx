"use client";

import { AlertTriangle, PiggyBank, Package, Trash2 } from "lucide-react";
import type { ResumenInteligencia } from "@/lib/types";

function euros(valor: number): string {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
  }).format(valor);
}

/**
 * Resumen económico y de salud del inventario: valor estimado, ítems bajo
 * mínimo, caducidades y desperdicio acumulado del mes.
 */
export function WidgetResumenHogar({
  datos,
}: {
  datos: ResumenInteligencia;
}) {
  const desperdicio = datos.desperdicio_mes;

  const tarjetas = [
    {
      clave: "valor",
      icono: PiggyBank,
      color: "bg-emerald-500/15 text-emerald-400",
      etiqueta: "Valor del inventario",
      valor: euros(datos.valor_inventario),
      detalle: `${datos.total_items} ítems registrados`,
    },
    {
      clave: "minimo",
      icono: AlertTriangle,
      color:
        datos.items_bajo_minimo > 0
          ? "bg-rose-500/15 text-rose-400"
          : "bg-slate-500/15 text-slate-400",
      etiqueta: "Bajo mínimo",
      valor: String(datos.items_bajo_minimo),
      detalle:
        datos.items_bajo_minimo > 0
          ? "revisa la lista de reposición"
          : "todo por encima del mínimo",
    },
    {
      clave: "caducidad",
      icono: Package,
      color:
        datos.caducidades_7_dias > 0
          ? "bg-amber-500/15 text-amber-400"
          : "bg-slate-500/15 text-slate-400",
      etiqueta: "Caducan ≤ 7 días",
      valor: String(datos.caducidades_7_dias),
      detalle: "prueba el Rescue Chef",
    },
    {
      clave: "desperdicio",
      icono: Trash2,
      color:
        desperdicio.valor_total > 0
          ? "bg-fuchsia-500/15 text-fuchsia-400"
          : "bg-slate-500/15 text-slate-400",
      etiqueta: `Desperdicio ${desperdicio.mes}`,
      valor: euros(desperdicio.valor_total),
      detalle: `${desperdicio.total_registros} ${desperdicio.total_registros === 1 ? "merma" : "mermas"} registradas`,
    },
  ];

  return (
    <section aria-labelledby="titulo-resumen-hogar" className="tarjeta-bento sm:col-span-2">
      <h2 id="titulo-resumen-hogar" className="mb-4 text-base font-semibold">
        Salud del hogar
      </h2>
      <ul className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tarjetas.map(({ clave, icono: Icono, color, etiqueta, valor, detalle }) => (
          <li key={clave} className="rounded-xl border border-slate-700/30 bg-slate-900/40 p-3">
            <div className={`mb-2 flex size-8 items-center justify-center rounded-lg ${color}`}>
              <Icono className="size-4" />
            </div>
            <p className="text-xs text-slate-500">{etiqueta}</p>
            <p className="text-lg font-semibold tabular-nums text-slate-100">{valor}</p>
            <p className="mt-0.5 text-xs text-slate-500">{detalle}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
