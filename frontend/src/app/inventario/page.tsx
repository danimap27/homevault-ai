"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ErrorApi } from "@/lib/api";
import type { CategoriaItem, Consumible, Ubicacion } from "@/lib/types";
import { Cargando, ErrorWidget } from "@/components/estado-async";
import { Escaner } from "@/components/escaner";

/**
 * Inventario por zonas con pestañas. Las zonas mezclan ubicaciones físicas
 * (nevera, congelador, despensa) y categorías de uso (limpieza, recambios,
 * botiquín), filtradas en cliente sobre una única descarga del inventario.
 */

type Zona =
  | { id: string; nombre: string; tipo: "ubicacion"; valor: Ubicacion }
  | { id: string; nombre: string; tipo: "categoria"; valor: CategoriaItem };

const ZONAS: Zona[] = [
  { id: "nevera", nombre: "Nevera", tipo: "ubicacion", valor: "nevera" },
  { id: "congelador", nombre: "Congelador", tipo: "ubicacion", valor: "congelador" },
  { id: "despensa", nombre: "Despensa", tipo: "ubicacion", valor: "despensa" },
  { id: "limpieza", nombre: "Limpieza", tipo: "categoria", valor: "limpieza" },
  { id: "recambios", nombre: "Recambios", tipo: "categoria", valor: "recambios_hogar" },
  { id: "botiquin", nombre: "Botiquín", tipo: "categoria", valor: "botiquin" },
];

function filtrarPorZona(items: Consumible[], zona: Zona): Consumible[] {
  return items.filter((item) =>
    zona.tipo === "ubicacion"
      ? item.ubicacion === zona.valor
      : item.categoria === zona.valor,
  );
}

export default function InventarioPage() {
  const [items, setItems] = useState<Consumible[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zonaActiva, setZonaActiva] = useState<Zona>(ZONAS[0]);
  const [escanerAbierto, setEscanerAbierto] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  const cargar = useCallback(() => {
    setError(null);
    api
      .getInventario()
      .then(setItems)
      .catch((err) =>
        setError(
          err instanceof ErrorApi
            ? `Error ${err.status}: ${err.message}`
            : "API no disponible",
        ),
      );
  }, []);

  useEffect(cargar, [cargar]);

  const visibles = useMemo(
    () => filtrarPorZona(items ?? [], zonaActiva),
    [items, zonaActiva],
  );

  const alEscanear = useCallback(
    (codigo: string) => {
      setEscanerAbierto(false);
      const encontrado = (items ?? []).find((i) => i.ean_barcode === codigo);
      if (encontrado) {
        // Cambia a la zona del ítem y avisa del resultado del escaneo.
        const zona =
          ZONAS.find(
            (z) =>
              (z.tipo === "ubicacion" && z.valor === encontrado.ubicacion) ||
              (z.tipo === "categoria" && z.valor === encontrado.categoria),
          ) ?? ZONAS[0];
        setZonaActiva(zona);
        setAviso(`Detectado: ${encontrado.nombre} (EAN ${codigo})`);
      } else {
        setAviso(`EAN ${codigo} no está en el inventario`);
      }
    },
    [items],
  );

  const consumir = async (item: Consumible) => {
    try {
      const res = await api.consumirItem(item.id, 1);
      setAviso(
        `Consumido 1 ${item.unidad} de ${item.nombre}` +
          (res.anadido_a_lista_compra ? " (añadido a la lista de la compra)" : ""),
      );
      cargar();
    } catch (err) {
      setAviso(
        err instanceof ErrorApi ? err.message : "No se pudo consumir el ítem",
      );
    }
  };

  const comprar = async (item: Consumible) => {
    try {
      await api.registrarCompra(item.id, 1, item.precio_unitario_estimado ?? 0);
      setAviso(`Compra registrada: +1 ${item.unidad} de ${item.nombre}`);
      cargar();
    } catch (err) {
      setAviso(
        err instanceof ErrorApi ? err.message : "No se pudo registrar la compra",
      );
    }
  };

  return (
    <div>
      <div
        role="tablist"
        aria-label="Zonas del inventario"
        className="mb-4 flex gap-2 overflow-x-auto pb-1"
      >
        {ZONAS.map((zona) => (
          <button
            key={zona.id}
            role="tab"
            aria-selected={zona.id === zonaActiva.id}
            onClick={() => setZonaActiva(zona)}
            className={`boton-tactil shrink-0 ${
              zona.id === zonaActiva.id
                ? "bg-carbon-900 text-white dark:bg-arena-100 dark:text-carbon-950"
                : "border border-arena-200 bg-white dark:border-carbon-800 dark:bg-carbon-900"
            }`}
          >
            {zona.nombre}
            <span className="ml-1 text-xs opacity-60">
              {items ? filtrarPorZona(items, zona).length : "…"}
            </span>
          </button>
        ))}
      </div>

      {aviso && (
        <p
          className="mb-3 rounded-xl border border-emerald-300 bg-emerald-50
            p-2.5 text-sm text-emerald-800 dark:border-emerald-900
            dark:bg-emerald-950/60 dark:text-emerald-300"
          role="status"
        >
          {aviso}
        </p>
      )}

      {error && <ErrorWidget mensaje={error} />}
      {!error && items === null && <Cargando />}
      {items !== null && visibles.length === 0 && (
        <p className="text-sm text-carbon-950/60 dark:text-arena-100/60">
          No hay ítems en {zonaActiva.nombre.toLowerCase()}.
        </p>
      )}

      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {visibles.map((item) => (
          <li key={item.id} className="tarjeta-bento">
            <div className="mb-2 flex items-start justify-between gap-2">
              <h3 className="min-w-0 font-semibold leading-tight">
                {item.nombre}
              </h3>
              <span className="shrink-0 text-sm font-medium">
                {item.stock_actual} {item.unidad}
              </span>
            </div>

            {/* Badges: lotes FIFO, reserva estratégica, bajo mínimo, caducidad */}
            <div className="mb-3 flex flex-wrap gap-1.5 text-xs">
              {item.lotes.length > 0 && (
                <span className="rounded-full bg-sky-100 px-2 py-0.5 text-sky-800 dark:bg-sky-950 dark:text-sky-300">
                  {item.lotes.length} {item.lotes.length === 1 ? "lote" : "lotes"}
                </span>
              )}
              {item.es_reserva_estrategica && (
                <span className="rounded-full bg-violet-100 px-2 py-0.5 text-violet-800 dark:bg-violet-950 dark:text-violet-300">
                  Reserva estratégica
                </span>
              )}
              {item.stock_actual <= item.stock_minimo && (
                <span className="rounded-full bg-red-100 px-2 py-0.5 text-red-800 dark:bg-red-950 dark:text-red-300">
                  Bajo mínimo
                </span>
              )}
              {item.fecha_caducidad_proxima && (
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                  Caduca {item.fecha_caducidad_proxima}
                </span>
              )}
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => consumir(item)}
                className="boton-secundario flex-1"
              >
                Consumir 1
              </button>
              <button
                type="button"
                onClick={() => comprar(item)}
                className="boton-primario flex-1"
              >
                + Compra
              </button>
            </div>
          </li>
        ))}
      </ul>

      {/* Botón flotante del escáner, al alcance del pulgar */}
      <button
        type="button"
        onClick={() => setEscanerAbierto(true)}
        aria-label="Abrir escáner de código de barras"
        className="fixed bottom-20 right-4 z-30 flex size-14 items-center
          justify-center rounded-full bg-emerald-600 text-white shadow-lg
          transition-transform active:scale-90 hover:bg-emerald-700"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="size-7" aria-hidden>
          <path strokeLinecap="round" d="M3 7V5a2 2 0 0 1 2-2h2m10 0h2a2 2 0 0 1 2 2v2m0 10v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M4 12h16" />
        </svg>
      </button>

      {escanerAbierto && (
        <Escaner alDetectar={alEscanear} alCerrar={() => setEscanerAbierto(false)} />
      )}
    </div>
  );
}
