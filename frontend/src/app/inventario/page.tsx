"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ScanBarcode } from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import type {
  RespuestaBarcode,
  RespuestaBarcodeNoEncontrado,
} from "@/lib/api";
import type { CategoriaItem, Consumible, Ubicacion } from "@/lib/types";
import { Cargando, ErrorWidget } from "@/components/estado-async";
import { Escaner } from "@/components/escaner";
import { ModalEscaneo } from "@/components/modal-escaneo";

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
  const [modalEscaneoAbierto, setModalEscaneoAbierto] = useState(false);
  const [resultadoEscaneo, setResultadoEscaneo] = useState<
    RespuestaBarcode | RespuestaBarcodeNoEncontrado | null
  >(null);
  const [eanEscaneado, setEanEscaneado] = useState("");
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
    async (codigo: string) => {
      setEscanerAbierto(false);
      setEanEscaneado(codigo);
      setResultadoEscaneo(null);
      setModalEscaneoAbierto(true);
      try {
        const res = await api.escanearBarcode(codigo);
        setResultadoEscaneo(res);
        if ("item" in res) {
          const zona =
            ZONAS.find(
              (z) =>
                (z.tipo === "ubicacion" && z.valor === res.item.ubicacion) ||
                (z.tipo === "categoria" && z.valor === res.item.categoria),
            ) ?? ZONAS[0];
          setZonaActiva(zona);
        }
      } catch (err) {
        setModalEscaneoAbierto(false);
        setAviso(
          err instanceof ErrorApi
            ? `Error ${err.status}: ${err.message}`
            : "No se pudo consultar el código",
        );
      }
    },
    [items],
  );

  const alExitoEscaneo = useCallback(
    (mensaje: string) => {
      setAviso(mensaje);
      cargar();
    },
    [cargar],
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
                ? "bg-slate-100 text-slate-950"
                : "border border-slate-700/50 bg-slate-900/60 text-slate-300"
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
          className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200"
          role="status"
        >
          {aviso}
        </p>
      )}

      {error && <ErrorWidget mensaje={error} />}
      {!error && items === null && <Cargando />}
      {items !== null && visibles.length === 0 && (
        <p className="text-sm text-slate-500">
          No hay ítems en {zonaActiva.nombre.toLowerCase()}.
        </p>
      )}

      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {visibles.map((item) => (
          <li key={item.id} className="tarjeta-bento">
            <div className="mb-2 flex items-start justify-between gap-2">
              <h3 className="min-w-0 font-semibold leading-tight text-slate-100">
                {item.nombre}
              </h3>
              <span className="shrink-0 text-sm font-medium text-slate-300">
                {item.stock_actual} {item.unidad}
              </span>
            </div>

            <div className="mb-3 flex flex-wrap gap-1.5 text-xs">
              {item.lotes.length > 0 && (
                <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-sky-300">
                  {item.lotes.length} {item.lotes.length === 1 ? "lote" : "lotes"}
                </span>
              )}
              {item.es_reserva_estrategica && (
                <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-violet-300">
                  Reserva estratégica
                </span>
              )}
              {item.stock_actual <= item.stock_minimo && (
                <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-rose-300">
                  Bajo mínimo
                </span>
              )}
              {item.fecha_caducidad_proxima && (
                <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-amber-300">
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

      <button
        type="button"
        onClick={() => setEscanerAbierto(true)}
        aria-label="Abrir escáner de código de barras"
        className="fixed bottom-24 right-5 z-30 flex size-14 items-center justify-center rounded-full bg-emerald-600 text-white shadow-lg shadow-emerald-900/30 transition-all duration-200 hover:scale-110 hover:bg-emerald-500 active:scale-95"
      >
        <ScanBarcode className="size-7" />
      </button>

      {escanerAbierto && (
        <Escaner alDetectar={alEscanear} alCerrar={() => setEscanerAbierto(false)} />
      )}

      {modalEscaneoAbierto && (
        <ModalEscaneo
          resultado={resultadoEscaneo}
          ean={eanEscaneado}
          alCerrar={() => setModalEscaneoAbierto(false)}
          alExito={alExitoEscaneo}
        />
      )}
    </div>
  );
}
