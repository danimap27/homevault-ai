"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Clock, ShieldCheck } from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import type { ItemCaducidad } from "@/lib/types";
import { Cargando, ErrorWidget } from "@/components/estado-async";

type NivelSemaforo = "rojo" | "amarillo" | "verde";

function nivelDe(diasRestantes: number): NivelSemaforo {
  if (diasRestantes <= 0) return "rojo";
  if (diasRestantes <= 2) return "amarillo";
  return "verde";
}

const ESTILOS_NIVEL: Record<NivelSemaforo, string> = {
  rojo: "border-rose-500/20 bg-rose-500/10 text-rose-200",
  amarillo:
    "border-amber-500/20 bg-amber-500/10 text-amber-200",
  verde: "border-emerald-500/20 bg-emerald-500/10 text-emerald-200",
};

const ICONO_NIVEL = {
  rojo: AlertTriangle,
  amarillo: Clock,
  verde: ShieldCheck,
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
      <h2 id="titulo-caducidades" className="mb-4 text-base font-semibold">
        Semáforo de caducidades
      </h2>
      {error && <ErrorWidget mensaje={error} />}
      {!error && items === null && <Cargando />}
      {items !== null && items.length === 0 && (
        <p className="text-sm text-slate-500">
          Nada caduca en los próximos 5 días.
        </p>
      )}
      {items !== null && items.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-3">
          {(["rojo", "amarillo", "verde"] as const).map((nivel) => {
            const grupo = porNivel(nivel);
            const Icono = ICONO_NIVEL[nivel];
            return (
              <li
                key={nivel}
                className={`rounded-xl border p-3 ${ESTILOS_NIVEL[nivel]}`}
              >
                <div className="mb-2 flex items-center gap-2">
                  <Icono className="size-4" />
                  <p className="text-xs font-bold uppercase tracking-wide">
                    {ETIQUETA_DIAS[nivel]} · {grupo.length}
                  </p>
                </div>
                <ul className="space-y-1 text-sm">
                  {grupo.slice(0, 4).map((item) => (
                    <li key={`${item.item_id}-${item.origen}`} className="truncate">
                      {item.nombre}
                      <span className="opacity-70">
                        {" "}(
                        {item.dias_restantes <= 0
                          ? "hoy/ayer"
                          : `${item.dias_restantes} d`}
                        )
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
