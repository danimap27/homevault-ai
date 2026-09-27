"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  Check,
  Loader2,
  PackageX,
  Pencil,
  Plus,
  ScanBarcode,
  Search,
  ShoppingCart,
  Store,
  Trash2,
  X,
} from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import type {
  RespuestaBarcode,
  RespuestaBarcodeNoEncontrado,
} from "@/lib/api";
import type {
  Categoria,
  CategoriaItem,
  Consumible,
  PrediccionAgotamiento,
  Supermercado,
  Ubicacion,
  Unidad,
} from "@/lib/types";
import { Cargando, ErrorWidget } from "@/components/estado-async";
import { Escaner } from "@/components/escaner";
import { ModalEscaneo } from "@/components/modal-escaneo";
import { ModalMerma } from "@/components/modal-merma";
import { formatearCantidad } from "@/lib/formato";

const UBICACIONES: { id: Ubicacion; nombre: string }[] = [
  { id: "nevera", nombre: "Nevera" },
  { id: "congelador", nombre: "Congelador" },
  { id: "despensa", nombre: "Despensa" },
  { id: "bano", nombre: "Baño" },
  { id: "trastero", nombre: "Trastero" },
];

const UNIDADES: Unidad[] = [
  "litros",
  "kg",
  "gramos",
  "unidades",
  "pastillas",
  "dosis",
];

const SIN_FILTRO = "__todas__";

function textoDiasStock(dias: number): string {
  if (dias < 1) return "<1 d";
  return `${Math.round(dias)} d`;
}

function estiloPrediccion(dias: number): string {
  if (dias <= 3) return "bg-rose-500/15 text-rose-300";
  if (dias <= 7) return "bg-amber-500/15 text-amber-300";
  return "bg-fuchsia-500/15 text-fuchsia-300";
}

function nombreCategoria(categorias: Categoria[], id?: string | null): string {
  if (!id) return "Sin categoría";
  return categorias.find((c) => c.id === id)?.nombre ?? id;
}

const DIAS_CADUCA_PRONTO = 7;

/** Texto sin tildes y en minúsculas para búsquedas tolerantes. */
function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

/** Ítems que requieren decisión: sin stock o al límite del mínimo. */
function necesitaAtencion(item: Consumible): boolean {
  return (
    item.stock_actual <= 0 ||
    (item.stock_minimo > 0 && item.stock_actual <= item.stock_minimo)
  );
}

/** Caduca en los próximos `DIAS_CADUCA_PRONTO` días. */
function caducaPronto(item: Consumible): boolean {
  if (!item.fecha_caducidad_proxima) return false;
  const dias =
    (new Date(`${item.fecha_caducidad_proxima}T00:00:00`).getTime() -
      Date.now()) /
    86_400_000;
  return dias <= DIAS_CADUCA_PRONTO;
}

/** Peso del orden «atención primero»: 0 sin stock → 3 sin urgencia. */
function pesoAtencion(item: Consumible): number {
  if (item.stock_actual <= 0) return 0;
  if (item.stock_minimo > 0 && item.stock_actual <= item.stock_minimo) return 1;
  if (caducaPronto(item)) return 2;
  return 3;
}

export default function InventarioPage() {
  const [items, setItems] = useState<Consumible[] | null>(null);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [ubicacionActiva, setUbicacionActiva] = useState<Ubicacion | typeof SIN_FILTRO>(
    SIN_FILTRO,
  );
  const [categoriaActiva, setCategoriaActiva] = useState<CategoriaItem | typeof SIN_FILTRO>(
    SIN_FILTRO,
  );
  const [estadoActivo, setEstadoActivo] = useState<
    "atencion" | "caduca" | typeof SIN_FILTRO
  >(SIN_FILTRO);
  const [orden, setOrden] = useState<"atencion" | "nombre" | "caducidad">(
    "atencion",
  );
  const [busqueda, setBusqueda] = useState("");
  const [escanerAbierto, setEscanerAbierto] = useState(false);
  const [modalEscaneoAbierto, setModalEscaneoAbierto] = useState(false);
  const [resultadoEscaneo, setResultadoEscaneo] = useState<
    RespuestaBarcode | RespuestaBarcodeNoEncontrado | null
  >(null);
  const [eanEscaneado, setEanEscaneado] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);
  const [itemCompra, setItemCompra] = useState<Consumible | null>(null);
  const [itemEdicion, setItemEdicion] = useState<Consumible | null>(null);
  const [modalNuevoAbierto, setModalNuevoAbierto] = useState(false);
  const [confirmarBorrado, setConfirmarBorrado] = useState<Consumible | null>(null);
  const [itemMerma, setItemMerma] = useState<Consumible | null>(null);
  const [predicciones, setPredicciones] = useState<
    Record<string, PrediccionAgotamiento>
  >({});

  const cargar = useCallback(() => {
    setError(null);
    Promise.all([api.getInventario(), api.getCategorias()])
      .then(([lista, cats]) => {
        setItems(lista);
        setCategorias(cats.sort((a, b) => a.orden - b.orden));
      })
      .catch((err) =>
        setError(
          err instanceof ErrorApi
            ? `Error ${err.status}: ${err.message}`
            : "API no disponible",
        ),
      );
    // Las predicciones son un extra: si fallan, la página sigue operativa
    api
      .getPredicciones()
      .then((preds) =>
        setPredicciones(
          Object.fromEntries(preds.map((p) => [p.item_id, p])),
        ),
      )
      .catch(() => setPredicciones({}));
  }, []);

  useEffect(cargar, [cargar]);

  const visibles = useMemo(() => {
    const consulta = normalizar(busqueda.trim());
    const filtrados = (items ?? []).filter((item) => {
      const okUbicacion =
        ubicacionActiva === SIN_FILTRO || item.ubicacion === ubicacionActiva;
      const okCategoria =
        categoriaActiva === SIN_FILTRO || item.categoria === categoriaActiva;
      const okEstado =
        estadoActivo === SIN_FILTRO ||
        (estadoActivo === "atencion"
          ? necesitaAtencion(item)
          : caducaPronto(item));
      const okBusqueda =
        consulta === "" || normalizar(item.nombre).includes(consulta);
      return okUbicacion && okCategoria && okEstado && okBusqueda;
    });
    const porNombre = (a: Consumible, b: Consumible) =>
      a.nombre.localeCompare(b.nombre, "es");
    if (orden === "nombre") return [...filtrados].sort(porNombre);
    if (orden === "caducidad") {
      return [...filtrados].sort((a, b) => {
        const fa = a.fecha_caducidad_proxima ?? "9999-99-99";
        const fb = b.fecha_caducidad_proxima ?? "9999-99-99";
        return fa === fb ? porNombre(a, b) : fa.localeCompare(fb);
      });
    }
    return [...filtrados].sort(
      (a, b) => pesoAtencion(a) - pesoAtencion(b) || porNombre(a, b),
    );
  }, [items, ubicacionActiva, categoriaActiva, estadoActivo, orden, busqueda]);

  const nAtencion = useMemo(
    () => (items ?? []).filter(necesitaAtencion).length,
    [items],
  );
  const nCaducaPronto = useMemo(
    () => (items ?? []).filter(caducaPronto).length,
    [items],
  );

  const contarPorUbicacion = useCallback(
    (ubicacion: Ubicacion) =>
      (items ?? []).filter(
        (item) =>
          item.ubicacion === ubicacion &&
          (categoriaActiva === SIN_FILTRO || item.categoria === categoriaActiva),
      ).length,
    [items, categoriaActiva],
  );

  const contarPorCategoria = useCallback(
    (categoria: CategoriaItem) =>
      (items ?? []).filter(
        (item) =>
          item.categoria === categoria &&
          (ubicacionActiva === SIN_FILTRO || item.ubicacion === ubicacionActiva),
      ).length,
    [items, ubicacionActiva],
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
          setUbicacionActiva(res.item.ubicacion);
          setCategoriaActiva(res.item.categoria);
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
    [],
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

  const borrar = async (item: Consumible) => {
    try {
      await api.borrarItem(item.id);
      setAviso(`Ítem "${item.nombre}" eliminado`);
      setConfirmarBorrado(null);
      cargar();
    } catch (err) {
      setAviso(
        err instanceof ErrorApi ? err.message : "No se pudo borrar el ítem",
      );
    }
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-2">
        <h2 className="mr-auto text-lg font-semibold text-slate-100">Inventario</h2>
        <button
          type="button"
          onClick={() => setModalNuevoAbierto(true)}
          className="boton-primario shrink-0"
        >
          <Plus className="size-4" /> Nuevo
        </button>
      </div>

      <div className="mb-4 space-y-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
          <input
            value={busqueda}
            onChange={(ev) => setBusqueda(ev.target.value)}
            placeholder="Buscar producto…"
            className="input-premium w-full pl-9"
            aria-label="Buscar en el inventario"
          />
          {busqueda && (
            <button
              type="button"
              onClick={() => setBusqueda("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-400 transition-colors hover:text-slate-100"
              aria-label="Limpiar búsqueda"
            >
              <X className="size-4" />
            </button>
          )}
        </div>
        <div className="chips-scroll">
          <button
            type="button"
            onClick={() => setUbicacionActiva(SIN_FILTRO)}
            className={`boton-tactil ${
              ubicacionActiva === SIN_FILTRO
                ? "bg-slate-100 text-slate-950"
                : "border border-slate-700/50 bg-slate-900/60 text-slate-300"
            }`}
          >
            Todas
            <span className="ml-1 text-xs opacity-60">
              {items?.length ?? "…"}
            </span>
          </button>
          {UBICACIONES.map((u) => (
            <button
              key={u.id}
              type="button"
              onClick={() => setUbicacionActiva(u.id)}
              className={`boton-tactil ${
                ubicacionActiva === u.id
                  ? "bg-slate-100 text-slate-950"
                  : "border border-slate-700/50 bg-slate-900/60 text-slate-300"
              }`}
            >
              {u.nombre}
              <span className="ml-1 text-xs opacity-60">
                {items ? contarPorUbicacion(u.id) : "…"}
              </span>
            </button>
          ))}
        </div>

        <div className="chips-scroll">
          <button
            type="button"
            onClick={() => setCategoriaActiva(SIN_FILTRO)}
            className={`boton-tactil ${
              categoriaActiva === SIN_FILTRO
                ? "bg-slate-100 text-slate-950"
                : "border border-slate-700/50 bg-slate-900/60 text-slate-300"
            }`}
          >
            Todas
          </button>
          {categorias.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setCategoriaActiva(c.id)}
              className={`boton-tactil ${
                categoriaActiva === c.id
                  ? "text-slate-950"
                  : "border border-slate-700/50 bg-slate-900/60 text-slate-200"
              }`}
              style={
                categoriaActiva === c.id
                  ? { backgroundColor: c.color }
                  : { borderColor: `${c.color}60`, color: c.color }
              }
            >
              <span>{c.icono}</span>
              {c.nombre}
              <span className="ml-1 text-xs opacity-70">
                {items ? contarPorCategoria(c.id) : "…"}
              </span>
            </button>
          ))}
        </div>

        <div className="chips-scroll items-center">
          <button
            type="button"
            onClick={() =>
              setEstadoActivo((actual) =>
                actual === "atencion" ? SIN_FILTRO : "atencion",
              )
            }
            aria-pressed={estadoActivo === "atencion"}
            className={`boton-tactil ${
              estadoActivo === "atencion"
                ? "bg-rose-500/20 text-rose-200 ring-1 ring-rose-400/50"
                : "border border-rose-500/30 bg-slate-900/60 text-rose-300/90"
            }`}
          >
            ⚠️ Atención
            <span className="ml-1 text-xs opacity-70">
              {items ? nAtencion : "…"}
            </span>
          </button>
          <button
            type="button"
            onClick={() =>
              setEstadoActivo((actual) =>
                actual === "caduca" ? SIN_FILTRO : "caduca",
              )
            }
            aria-pressed={estadoActivo === "caduca"}
            className={`boton-tactil ${
              estadoActivo === "caduca"
                ? "bg-amber-500/20 text-amber-200 ring-1 ring-amber-400/50"
                : "border border-amber-500/30 bg-slate-900/60 text-amber-300/90"
            }`}
          >
            ⏰ Caduca pronto
            <span className="ml-1 text-xs opacity-70">
              {items ? nCaducaPronto : "…"}
            </span>
          </button>
          <label className="ml-auto flex items-center gap-1.5 text-xs text-slate-400">
            Orden
            <select
              value={orden}
              onChange={(ev) =>
                setOrden(ev.target.value as "atencion" | "nombre" | "caducidad")
              }
              className="rounded-lg border border-slate-700/50 bg-slate-900/80 px-2 py-1.5 text-xs text-slate-200"
              aria-label="Ordenar inventario"
            >
              <option value="atencion">Atención primero</option>
              <option value="caducidad">Caducidad</option>
              <option value="nombre">Nombre (A-Z)</option>
            </select>
          </label>
        </div>
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
          No hay ítems con los filtros activos.
        </p>
      )}

      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {visibles.map((item) => {
          const pred = predicciones[item.id];
          return (
          <li key={item.id} className="tarjeta-bento">
            <div className="mb-2 flex items-start justify-between gap-2">
              <h3 className="min-w-0 font-semibold leading-tight text-slate-100">
                {item.nombre}
              </h3>
              <span className="shrink-0 text-sm font-medium text-slate-300">
                {formatearCantidad(item.stock_actual, item.unidad)}
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
              {item.stock_actual <= 0 ? (
                <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-rose-300">
                  Sin stock
                </span>
              ) : item.stock_actual <= item.stock_minimo ? (
                <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-rose-300">
                  Bajo mínimo
                </span>
              ) : null}
              {item.fecha_caducidad_proxima && (
                <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-amber-300">
                  Caduca {item.fecha_caducidad_proxima}
                </span>
              )}
              {pred && (
                <span
                  className={`rounded-full px-2 py-0.5 ${estiloPrediccion(pred.dias_restantes)}`}
                  title={`Agotamiento estimado: ${pred.fecha_estimada_agotamiento} · confianza ${pred.confianza} · ritmo ${pred.tasa_diaria} ${item.unidad}/día`}
                >
                  ≈{textoDiasStock(pred.dias_restantes)} de stock
                </span>
              )}
              {item.auto_lista_compra && (
                <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-emerald-300">
                  Auto-compra
                </span>
              )}
              <span className="rounded-full bg-slate-700/50 px-2 py-0.5 text-slate-300">
                {nombreCategoria(categorias, item.categoria)}
              </span>
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => consumir(item)}
                disabled={item.stock_actual <= 0}
                className="boton-secundario flex-1 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {item.stock_actual <= 0 ? "Sin stock" : "Consumir 1"}
              </button>
              <button
                type="button"
                onClick={() => setItemCompra(item)}
                className="boton-primario flex-1"
              >
                + Compra
              </button>
            </div>

            <div className="mt-3 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setItemMerma(item)}
                className="rounded-lg p-2 text-amber-400/90 transition-colors hover:bg-amber-950/30"
                aria-label="Registrar merma (producto tirado)"
                title="Registrar merma (producto tirado)"
              >
                <PackageX className="size-4" />
              </button>
              <button
                type="button"
                onClick={() => setItemEdicion(item)}
                className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-100"
                aria-label="Editar ítem"
              >
                <Pencil className="size-4" />
              </button>
              <button
                type="button"
                onClick={() => setConfirmarBorrado(item)}
                className="rounded-lg p-2 text-rose-400 transition-colors hover:bg-rose-950/30"
                aria-label="Borrar ítem"
              >
                <Trash2 className="size-4" />
              </button>
            </div>
          </li>
          );
        })}
      </ul>

      <button
        type="button"
        onClick={() => setEscanerAbierto(true)}
        aria-label="Abrir escáner de código de barras"
        className="fixed bottom-24 right-4 z-30 flex size-12 items-center justify-center rounded-full bg-emerald-600 text-white shadow-lg shadow-emerald-900/30 transition-all duration-200 hover:scale-110 hover:bg-emerald-500 active:scale-95 sm:right-5 sm:size-14"
      >
        <ScanBarcode className="size-6 sm:size-7" />
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

      {itemCompra && (
        <ModalCompra
          item={itemCompra}
          onCerrar={() => setItemCompra(null)}
          onExito={(mensaje) => {
            setAviso(mensaje);
            cargar();
          }}
        />
      )}

      {itemMerma && (
        <ModalMerma
          item={itemMerma}
          onCerrar={() => setItemMerma(null)}
          onExito={(mensaje) => {
            setAviso(mensaje);
            setItemMerma(null);
            cargar();
          }}
        />
      )}

      {(modalNuevoAbierto || itemEdicion) && (
        <ModalItem
          item={itemEdicion}
          categorias={categorias}
          onCerrar={() => {
            setModalNuevoAbierto(false);
            setItemEdicion(null);
          }}
          onExito={(mensaje) => {
            setAviso(mensaje);
            cargar();
          }}
        />
      )}

      {confirmarBorrado && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
          onClick={() => setConfirmarBorrado(null)}
        >
          <div
            className="w-full max-w-sm rounded-3xl border border-slate-700/30 bg-slate-900/90 p-6 shadow-2xl"
            onClick={(ev) => ev.stopPropagation()}
          >
            <h3 className="mb-2 text-lg font-semibold text-slate-100">¿Borrar ítem?</h3>
            <p className="mb-4 text-sm text-slate-400">
              Se eliminará permanentemente <strong>{confirmarBorrado.nombre}</strong>.
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setConfirmarBorrado(null)}
                className="boton-secundario flex-1"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => borrar(confirmarBorrado)}
                className="boton-peligro flex-1"
              >
                <Trash2 className="size-4" /> Borrar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ModalCompra({
  item,
  onCerrar,
  onExito,
}: {
  item: Consumible;
  onCerrar: () => void;
  onExito: (mensaje: string) => void;
}) {
  const [cantidad, setCantidad] = useState(1);
  const [precio, setPrecio] = useState(item.precio_unitario_estimado ?? 0);
  const [caducidad, setCaducidad] = useState("");
  const [supermercadoId, setSupermercadoId] = useState<string>("");
  const [supermercados, setSupermercados] = useState<Supermercado[]>([]);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getSupermercados().then((lista) => {
      setSupermercados(lista);
      const pred = lista.find((s) => s.predeterminado);
      if (pred) setSupermercadoId(pred.id);
    });
  }, []);

  const enviar = async () => {
    if (cantidad <= 0) {
      setError("La cantidad debe ser mayor que 0");
      return;
    }
    setCargando(true);
    setError(null);
    try {
      const res = await api.registrarCompra(
        item.id,
        cantidad,
        precio,
        caducidad || undefined,
        supermercadoId || undefined,
      );
      const partes = [
        `Compra registrada: +${cantidad} ${item.unidad} de ${item.nombre}`,
      ];
      if (res.tachado_de_lista_compra) partes.push("tachado de la lista");
      onExito(partes.join(" · "));
      onCerrar();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo registrar la compra",
      );
    } finally {
      setCargando(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
      onClick={onCerrar}
    >
      <div
        className="w-full max-w-md rounded-3xl border border-slate-700/30 bg-slate-900/90 p-6 shadow-2xl"
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-slate-100">Registrar compra</h3>
          <button type="button" onClick={onCerrar} className="boton-secundario">
            <X className="size-4" />
          </button>
        </div>
        <p className="mb-4 text-sm text-slate-400">{item.nombre}</p>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Cantidad
              </label>
              <input
                type="number"
                min="1"
                step={item.unidad === "unidades" ? 1 : 0.01}
                value={cantidad}
                onChange={(ev) => setCantidad(Number(ev.target.value))}
                className="input-premium"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Precio unitario (€)
              </label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={precio}
                onChange={(ev) => setPrecio(Number(ev.target.value))}
                className="input-premium"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-300">
              <CalendarDays className="mr-1 inline size-4" />
              Fecha de caducidad
            </label>
            <input
              type="date"
              value={caducidad}
              onChange={(ev) => setCaducidad(ev.target.value)}
              className="input-premium"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-300">
              <Store className="mr-1 inline size-4" />
              Supermercado
            </label>
            <select
              value={supermercadoId}
              onChange={(ev) => setSupermercadoId(ev.target.value)}
              className="input-premium"
            >
              <option value="">Sin supermercado</option>
              {supermercados.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nombre}
                  {s.predeterminado ? " ★" : ""}
                </option>
              ))}
            </select>
          </div>

          {error && (
            <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-2 text-sm text-rose-200">
              {error}
            </p>
          )}

          <button
            type="button"
            onClick={enviar}
            disabled={cargando}
            className="boton-primario w-full justify-center"
          >
            {cargando ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <>
                <ShoppingCart className="size-4" /> Guardar compra
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function ModalItem({
  item,
  categorias,
  onCerrar,
  onExito,
}: {
  item: Consumible | null;
  categorias: Categoria[];
  onCerrar: () => void;
  onExito: (mensaje: string) => void;
}) {
  const editando = item !== null;
  const categoriaDefault = categorias[0]?.id ?? "";
  const [nombre, setNombre] = useState(item?.nombre ?? "");
  const [categoria, setCategoria] = useState<CategoriaItem>(
    item?.categoria ?? categoriaDefault,
  );
  const [ubicacion, setUbicacion] = useState<Ubicacion>(item?.ubicacion ?? "despensa");
  const [unidad, setUnidad] = useState<Unidad>(item?.unidad ?? "unidades");
  const [stockMinimo, setStockMinimo] = useState(item?.stock_minimo ?? 0);
  const [precio, setPrecio] = useState(item?.precio_unitario_estimado ?? 0);
  const [ean, setEan] = useState(item?.ean_barcode ?? "");
  const [autoLista, setAutoLista] = useState(item?.auto_lista_compra ?? false);
  const [tags, setTags] = useState(item?.tags.join(", ") ?? "");
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (categorias.length > 0 && !categoria) {
      setCategoria(categorias[0].id);
    }
  }, [categorias, categoria]);

  const enviar = async () => {
    if (!nombre.trim()) {
      setError("El nombre es obligatorio");
      return;
    }
    setCargando(true);
    setError(null);
    try {
      const payload = {
        nombre: nombre.trim(),
        categoria,
        ubicacion,
        unidad,
        stock_minimo: Number(stockMinimo) || 0,
        precio_unitario_estimado: precio ? Number(precio) : null,
        ean_barcode: ean.trim() || null,
        auto_lista_compra: autoLista,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      };
      if (editando) {
        const cambioUbicacion = ubicacion !== item.ubicacion;
        const cambioCategoria = categoria !== item.categoria;
        let actualizado = item;
        if (cambioUbicacion || cambioCategoria) {
          actualizado = await api.moverItem(item.id, {
            ...(cambioUbicacion ? { ubicacion } : {}),
            ...(cambioCategoria ? { categoria } : {}),
          });
        }
        const resto: Record<string, unknown> = {};
        if (payload.nombre !== item.nombre) resto.nombre = payload.nombre;
        if (payload.unidad !== item.unidad) resto.unidad = payload.unidad;
        if (payload.stock_minimo !== item.stock_minimo)
          resto.stock_minimo = payload.stock_minimo;
        if (payload.precio_unitario_estimado !== item.precio_unitario_estimado)
          resto.precio_unitario_estimado = payload.precio_unitario_estimado;
        if (payload.ean_barcode !== item.ean_barcode)
          resto.ean_barcode = payload.ean_barcode;
        if (payload.auto_lista_compra !== item.auto_lista_compra)
          resto.auto_lista_compra = payload.auto_lista_compra;
        const tagsOrdenados = payload.tags.slice().sort();
        const itemTagsOrdenados = item.tags.slice().sort();
        if (JSON.stringify(tagsOrdenados) !== JSON.stringify(itemTagsOrdenados))
          resto.tags = payload.tags;
        if (Object.keys(resto).length > 0) {
          actualizado = await api.actualizarItem(item.id, resto);
        }
        onExito(`Ítem "${actualizado.nombre}" actualizado`);
      } else {
        const creado = await api.crearItem(payload);
        onExito(`Ítem "${creado.nombre}" creado`);
      }
      onCerrar();
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo guardar el ítem");
    } finally {
      setCargando(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
      onClick={onCerrar}
    >
      <div
        className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-3xl border border-slate-700/30 bg-slate-900/90 p-6 shadow-2xl"
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-slate-100">
            {editando ? "Editar ítem" : "Nuevo ítem"}
          </h3>
          <button type="button" onClick={onCerrar} className="boton-secundario">
            <X className="size-4" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-300">
              Nombre
            </label>
            <input
              type="text"
              value={nombre}
              onChange={(ev) => setNombre(ev.target.value)}
              className="input-premium"
              placeholder="Ej. Leche entera"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Categoría
              </label>
              <select
                value={categoria}
                onChange={(ev) => setCategoria(ev.target.value as CategoriaItem)}
                className="input-premium"
              >
                {categorias.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.icono} {c.nombre}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Ubicación
              </label>
              <select
                value={ubicacion}
                onChange={(ev) => setUbicacion(ev.target.value as Ubicacion)}
                className="input-premium"
              >
                {UBICACIONES.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.nombre}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Unidad
              </label>
              <select
                value={unidad}
                onChange={(ev) => setUnidad(ev.target.value as Unidad)}
                className="input-premium"
              >
                {UNIDADES.map((u) => (
                  <option key={u} value={u}>
                    {u}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Stock mínimo
              </label>
              <input
                type="number"
                min="0"
                step={unidad === "unidades" ? 1 : 0.01}
                value={stockMinimo}
                onChange={(ev) => setStockMinimo(Number(ev.target.value))}
                className="input-premium"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Precio unitario (€)
              </label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={precio}
                onChange={(ev) => setPrecio(Number(ev.target.value))}
                className="input-premium"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                EAN
              </label>
              <input
                type="text"
                value={ean}
                onChange={(ev) => setEan(ev.target.value)}
                className="input-premium"
                placeholder="Opcional"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-300">
              Etiquetas (separadas por comas)
            </label>
            <input
              type="text"
              value={tags}
              onChange={(ev) => setTags(ev.target.value)}
              className="input-premium"
              placeholder="gluten, fresco, oferta"
            />
          </div>

          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={autoLista}
              onChange={(ev) => setAutoLista(ev.target.checked)}
              className="size-5 accent-emerald-600"
            />
            Añadir automáticamente a la lista de la compra si baja del mínimo
          </label>

          {error && (
            <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-2 text-sm text-rose-200">
              {error}
            </p>
          )}

          <button
            type="button"
            onClick={enviar}
            disabled={cargando}
            className="boton-primario w-full justify-center"
          >
            {cargando ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <>
                <Check className="size-4" /> Guardar ítem
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
