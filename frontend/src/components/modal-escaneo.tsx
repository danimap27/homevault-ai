"use client";

import { useCallback, useRef, useState } from "react";
import {
  Camera,
  Check,
  Loader2,
  Package,
  Plus,
  ShoppingCart,
  Tag,
  Trash2,
  X,
} from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import type {
  RespuestaBarcode,
  RespuestaBarcodeNoEncontrado,
} from "@/lib/api";
import type { CategoriaItem, Ubicacion, Unidad } from "@/lib/types";

type ResultadoEscaneo = RespuestaBarcode | RespuestaBarcodeNoEncontrado;

interface ModalEscaneoProps {
  resultado: ResultadoEscaneo | null;
  ean: string;
  alCerrar: () => void;
  alExito: (mensaje: string) => void;
}

const CATEGORIAS: { valor: CategoriaItem; etiqueta: string }[] = [
  { valor: "lacteos", etiqueta: "Lácteos" },
  { valor: "congelados", etiqueta: "Congelados" },
  { valor: "despensa_seca", etiqueta: "Despensa seca" },
  { valor: "limpieza", etiqueta: "Limpieza" },
  { valor: "recambios_hogar", etiqueta: "Recambios del hogar" },
  { valor: "botiquin", etiqueta: "Botiquín" },
];

const UBICACIONES: { valor: Ubicacion; etiqueta: string }[] = [
  { valor: "nevera", etiqueta: "Nevera" },
  { valor: "congelador", etiqueta: "Congelador" },
  { valor: "despensa", etiqueta: "Despensa" },
  { valor: "bano", etiqueta: "Baño" },
  { valor: "trastero", etiqueta: "Trastero" },
];

const UNIDADES: { valor: Unidad; etiqueta: string }[] = [
  { valor: "unidades", etiqueta: "Unidades" },
  { valor: "kg", etiqueta: "Kilogramos" },
  { valor: "gramos", etiqueta: "Gramos" },
  { valor: "litros", etiqueta: "Litros" },
  { valor: "pastillas", etiqueta: "Pastillas" },
  { valor: "dosis", etiqueta: "Dosis" },
];

function esEncontrado(
  resultado: ResultadoEscaneo,
): resultado is RespuestaBarcode {
  return "item" in resultado;
}

export function ModalEscaneo({
  resultado,
  ean,
  alCerrar,
  alExito,
}: ModalEscaneoProps) {
  const [cargando, setCargando] = useState(false);
  const [mensaje, setMensaje] = useState<{
    texto: string;
    tipo: "exito" | "error";
  } | null>(null);

  // Formulario de producto no encontrado
  const [nombre, setNombre] = useState("");
  const [categoria, setCategoria] = useState<CategoriaItem>("despensa_seca");
  const [ubicacion, setUbicacion] = useState<Ubicacion>("despensa");
  const [unidad, setUnidad] = useState<Unidad>("unidades");
  const [precio, setPrecio] = useState("");
  const [mergeTargetId, setMergeTargetId] = useState("");
  const [fotoProducto, setFotoProducto] = useState<File | null>(null);
  const [fotoPrecio, setFotoPrecio] = useState<File | null>(null);

  const inputProductoRef = useRef<HTMLInputElement>(null);
  const inputPrecioRef = useRef<HTMLInputElement>(null);

  const mostrarExito = useCallback(
    (texto: string) => {
      setMensaje({ texto, tipo: "exito" });
      alExito(texto);
    },
    [alExito],
  );

  const mostrarError = useCallback((err: unknown) => {
    const texto =
      err instanceof ErrorApi ? err.message : "No se pudo completar la acción";
    setMensaje({ texto, tipo: "error" });
  }, []);

  const consumir = async (itemId: string, nombreItem: string) => {
    setCargando(true);
    setMensaje(null);
    try {
      const res = await api.consumirPorBarcode(ean, 1);
      const partes = [`Consumido 1 de ${nombreItem}`];
      if (res.resultado.anadido_a_lista_compra) {
        partes.push("añadido a la lista de la compra");
      }
      if (res.quitado_de_lista > 0) {
        partes.push(`quitado ${res.quitado_de_lista} de la lista`);
      }
      mostrarExito(partes.join(" · "));
    } catch (err) {
      mostrarError(err);
    } finally {
      setCargando(false);
    }
  };

  const comprar = async (item: { id: string; nombre: string; precio_unitario_estimado: number | null }) => {
    setCargando(true);
    setMensaje(null);
    try {
      const res = await api.registrarCompra(
        item.id,
        1,
        item.precio_unitario_estimado ?? 0,
      );
      const partes = [`Compra registrada: +1 ${item.nombre}`];
      if (res.tachado_de_lista_compra) {
        partes.push("tachado de la lista de la compra");
      }
      mostrarExito(partes.join(" · "));
    } catch (err) {
      mostrarError(err);
    } finally {
      setCargando(false);
    }
  };

  const quitarDeLista = async (itemId: string, nombreItem: string) => {
    setCargando(true);
    setMensaje(null);
    try {
      const res = await api.checkEntradaLista(itemId);
      mostrarExito(
        `${nombreItem}: ${res.tachadas} línea(s) quitada(s) de la lista de la compra`,
      );
    } catch (err) {
      if (err instanceof ErrorApi && err.status === 404) {
        setMensaje({
          texto: `${nombreItem} no está en la lista de la compra`,
          tipo: "error",
        });
      } else {
        mostrarError(err);
      }
    } finally {
      setCargando(false);
    }
  };

  const guardarNuevo = async (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!nombre.trim()) {
      setMensaje({ texto: "El nombre es obligatorio", tipo: "error" });
      return;
    }

    setCargando(true);
    setMensaje(null);
    try {
      const formData = new FormData();
      formData.append("ean", ean);
      formData.append("nombre", nombre.trim());
      formData.append("categoria", categoria);
      formData.append("ubicacion", ubicacion);
      formData.append("unidad", unidad);
      if (precio) formData.append("precio", precio);
      if (mergeTargetId) formData.append("merge_target_id", mergeTargetId);
      if (fotoProducto) formData.append("foto_producto", fotoProducto);
      if (fotoPrecio) formData.append("foto_precio", fotoPrecio);

      const item = await api.registrarBarcode(formData);
      mostrarExito(
        mergeTargetId
          ? `${item.nombre} fusionado correctamente`
          : `${item.nombre} registrado correctamente`,
      );
    } catch (err) {
      mostrarError(err);
    } finally {
      setCargando(false);
    }
  };

  if (!resultado) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Resultado del escaneo"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
      onClick={alCerrar}
    >
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl border border-slate-700/30 bg-slate-900/90 p-6 shadow-2xl shadow-black/40"
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">
              {esEncontrado(resultado) ? "Producto encontrado" : "Producto nuevo"}
            </h2>
            <p className="mt-0.5 text-sm text-slate-400">EAN {ean}</p>
          </div>
          <button
            type="button"
            onClick={alCerrar}
            aria-label="Cerrar"
            className="boton-secundario"
            disabled={cargando}
          >
            <X className="size-4" />
          </button>
        </div>

        {mensaje && (
          <div
            className={`mb-4 rounded-xl border p-3 text-sm ${
              mensaje.tipo === "exito"
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                : "border-rose-500/30 bg-rose-500/10 text-rose-200"
            }`}
            role="status"
          >
            {mensaje.texto}
          </div>
        )}

        {!resultado ? (
          <div className="flex flex-col items-center justify-center gap-3 py-10 text-slate-400">
            <Loader2 className="size-8 animate-spin text-emerald-500" />
            <p className="text-sm">Consultando código de barras…</p>
          </div>
        ) : esEncontrado(resultado) ? (
          <div className="space-y-5">
            <div className="flex items-center gap-4">
              <div className="flex size-20 items-center justify-center rounded-2xl border border-slate-700/30 bg-slate-800/60 text-slate-400">
                <Package className="size-8" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-slate-100">
                  {resultado.item.nombre}
                </h3>
                <p className="text-sm text-slate-300">
                  Stock: {resultado.item.stock_actual} {resultado.item.unidad}
                </p>
                <p className="text-xs capitalize text-slate-500">
                  {resultado.item.categoria.replace(/_/g, " ")} ·{" "}
                  {resultado.item.ubicacion}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2">
              <button
                type="button"
                onClick={() => consumir(resultado.item.id, resultado.item.nombre)}
                disabled={cargando}
                className="boton-primario justify-between"
              >
                <span className="flex items-center gap-2">
                  <Trash2 className="size-4" /> Consumir 1
                </span>
                {cargando && <Loader2 className="size-4 animate-spin" />}
              </button>
              <button
                type="button"
                onClick={() => comprar(resultado.item)}
                disabled={cargando}
                className="boton-secundario justify-between"
              >
                <span className="flex items-center gap-2">
                  <Plus className="size-4" /> + Compra
                </span>
                {cargando && <Loader2 className="size-4 animate-spin" />}
              </button>
              <button
                type="button"
                onClick={() => quitarDeLista(resultado.item.id, resultado.item.nombre)}
                disabled={cargando}
                className="boton-secundario justify-between border-violet-500/30 text-violet-200 hover:border-violet-500/50 hover:bg-violet-950/30"
              >
                <span className="flex items-center gap-2">
                  <ShoppingCart className="size-4" /> Quitar de la lista
                </span>
                {cargando && <Loader2 className="size-4 animate-spin" />}
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={guardarNuevo} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Nombre del producto *
              </label>
              <input
                type="text"
                value={nombre}
                onChange={(ev) => setNombre(ev.target.value)}
                placeholder="Ej: Leche entera"
                className="input-premium"
                required
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-300">
                  Categoría
                </label>
                <select
                  value={categoria}
                  onChange={(ev) => setCategoria(ev.target.value as CategoriaItem)}
                  className="input-premium"
                >
                  {CATEGORIAS.map((c) => (
                    <option key={c.valor} value={c.valor}>
                      {c.etiqueta}
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
                    <option key={u.valor} value={u.valor}>
                      {u.etiqueta}
                    </option>
                  ))}
                </select>
              </div>
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
                    <option key={u.valor} value={u.valor}>
                      {u.etiqueta}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Precio estimado (€)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={precio}
                onChange={(ev) => setPrecio(ev.target.value)}
                placeholder="0.00"
                className="input-premium"
              />
            </div>

            {resultado.sugerencias.length > 0 && (
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-300">
                  <Tag className="mr-1 inline size-4" />
                  Fusionar con producto existente
                </label>
                <select
                  value={mergeTargetId}
                  onChange={(ev) => setMergeTargetId(ev.target.value)}
                  className="input-premium"
                >
                  <option value="">No fusionar (crear nuevo)</option>
                  {resultado.sugerencias.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.nombre}
                      {s.ean_barcode ? ` · ${s.ean_barcode}` : ""}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div>
                <input
                  ref={inputProductoRef}
                  type="file"
                  accept="image/*"
                  capture="environment"
                  onChange={(ev) =>
                    setFotoProducto(ev.target.files?.[0] ?? null)
                  }
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => inputProductoRef.current?.click()}
                  className="boton-secundario w-full flex-col gap-1 py-3"
                >
                  <Camera className="size-5" />
                  <span className="text-xs">Foto del producto</span>
                </button>
                {fotoProducto && (
                  <p className="mt-1 truncate text-center text-xs text-emerald-300">
                    {fotoProducto.name}
                  </p>
                )}
              </div>

              <div>
                <input
                  ref={inputPrecioRef}
                  type="file"
                  accept="image/*"
                  capture="environment"
                  onChange={(ev) =>
                    setFotoPrecio(ev.target.files?.[0] ?? null)
                  }
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => inputPrecioRef.current?.click()}
                  className="boton-secundario w-full flex-col gap-1 py-3"
                >
                  <Tag className="size-5" />
                  <span className="text-xs">Foto del precio</span>
                </button>
                {fotoPrecio && (
                  <p className="mt-1 truncate text-center text-xs text-emerald-300">
                    {fotoPrecio.name}
                  </p>
                )}
              </div>
            </div>

            <button
              type="submit"
              disabled={cargando || !nombre.trim()}
              className="boton-primario w-full justify-center"
            >
              {cargando ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <>
                  <Check className="size-4" /> Guardar producto
                </>
              )}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
