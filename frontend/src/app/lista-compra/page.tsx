"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Check,
  CheckCircle2,
  Edit2,
  Loader2,
  Plus,
  Printer,
  Settings2,
  Share2,
  Store,
  Trash2,
  X,
} from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import { formatearCantidad } from "@/lib/formato";
import type { Categoria, EntradaListaCompra, Supermercado } from "@/lib/types";
import { Cargando, ErrorWidget } from "@/components/estado-async";

const CATEGORIA_GENERAL = "general";

function datosCategoria(
  categorias: Categoria[],
  id: string,
): Categoria | { id: string; nombre: string; color: string; icono: string; orden: number } {
  return (
    categorias.find((c) => c.id === id) ?? {
      id,
      nombre: id === CATEGORIA_GENERAL ? "General" : id.replace(/_/g, " "),
      color: "#64748b",
      icono: "🛒",
      orden: 9999,
    }
  );
}

export default function ListaCompraPage() {
  const [entradas, setEntradas] = useState<EntradaListaCompra[] | null>(null);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [supermercados, setSupermercados] = useState<Supermercado[]>([]);
  const [supermercadoId, setSupermercadoId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [modalSuper, setModalSuper] = useState(false);
  const [editando, setEditando] = useState<EntradaListaCompra | null>(null);

  const cargar = useCallback(() => {
    setError(null);
    Promise.all([api.getListaCompra(), api.getSupermercados(), api.getCategorias()])
      .then(([lista, supers, cats]) => {
        setEntradas(lista);
        setSupermercados(supers);
        setCategorias(cats.sort((a, b) => a.orden - b.orden));
        const pred = supers.find((s) => s.predeterminado);
        if (pred) setSupermercadoId(pred.id);
      })
      .catch((err) =>
        setError(
          err instanceof ErrorApi
            ? `Error ${err.status}: ${err.message}`
            : "API no disponible",
        ),
      );
  }, []);

  useEffect(cargar, [cargar]);

  const supermercadoActivo = useMemo(
    () => supermercados.find((s) => s.id === supermercadoId) ?? null,
    [supermercados, supermercadoId],
  );

  const porCategoria = useMemo(() => {
    const grupos = new Map<string, EntradaListaCompra[]>();
    for (const entrada of entradas ?? []) {
      const clave = entrada.categoria ?? CATEGORIA_GENERAL;
      grupos.set(clave, [...(grupos.get(clave) ?? []), entrada]);
    }
    return Array.from(grupos.entries()).sort(([idA], [idB]) => {
      const catA = datosCategoria(categorias, idA);
      const catB = datosCategoria(categorias, idB);
      return catA.orden - catB.orden || catA.nombre.localeCompare(catB.nombre);
    });
  }, [entradas, categorias]);

  const alternar = async (entrada: EntradaListaCompra) => {
    setEntradas(
      (prev) =>
        prev?.map((e) =>
          e.item_id === entrada.item_id ? { ...e, comprado: !e.comprado } : e,
        ) ?? null,
    );
    try {
      await api.checkEntradaLista(entrada.item_id);
    } catch (err) {
      setEntradas(
        (prev) =>
          prev?.map((e) =>
            e.item_id === entrada.item_id ? { ...e, comprado: entrada.comprado } : e,
          ) ?? null,
      );
      setAviso(
        err instanceof ErrorApi && err.status === 404
          ? "La entrada ya no está pendiente en la lista"
          : "No se pudo marcar la entrada",
      );
    }
  };

  const borrar = async (entrada: EntradaListaCompra) => {
    try {
      await api.borrarEntradaLista(entrada.item_id);
      setEntradas(
        (prev) => prev?.filter((e) => e.item_id !== entrada.item_id) ?? null,
      );
      setAviso(`"${entrada.nombre}" eliminado de la lista`);
    } catch (err) {
      setAviso(
        err instanceof ErrorApi ? err.message : "No se pudo borrar la entrada",
      );
    }
  };

  const guardarEdicion = async (cambios: {
    cantidad?: number;
    unidad?: string;
    categoria?: string;
  }) => {
    if (!editando) return;
    try {
      await api.editarEntradaLista(editando.item_id, cambios);
      setEntradas(
        (prev) =>
          prev?.map((e) =>
            e.item_id === editando.item_id ? { ...e, ...cambios } : e,
          ) ?? null,
      );
      setAviso(`"${editando.nombre}" actualizado`);
      setEditando(null);
    } catch (err) {
      setAviso(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo actualizar la entrada",
      );
    }
  };

  const textoLista = () =>
    porCategoria
      .map(([categoria, items]) => {
        const lineas = items.map(
          (e) =>
            `${e.comprado ? "[x]" : "[ ]"} ${e.nombre}` +
            (e.cantidad
              ? ` (${formatearCantidad(e.cantidad, e.unidad)})`
              : ""),
        );
        return `${categoria.toUpperCase()}\n${lineas.join("\n")}`;
      })
      .join("\n\n");

  const exportar = async () => {
    const texto = textoLista();
    try {
      if (navigator.share) {
        await navigator.share({ title: "Lista de la compra", text: texto });
        return;
      }
      await navigator.clipboard.writeText(texto);
      setAviso("Lista copiada al portapapeles");
    } catch {
      const blob = new Blob([texto], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.download = "lista-compra.txt";
      enlace.click();
      URL.revokeObjectURL(url);
      setAviso("Lista descargada como lista-compra.txt");
    }
  };

  const imprimir = async () => {
    try {
      const res = await api.imprimirListaCompra();
      setAviso(`Lista enviada a la impresora (${res.lineas} líneas)`);
    } catch {
      setAviso("Impresora térmica no disponible: usando impresión del navegador");
      setTimeout(() => window.print(), 300);
    }
  };

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h2 className="mr-auto text-lg font-semibold text-slate-100">
          Lista de la compra
        </h2>
        <button type="button" onClick={exportar} className="boton-secundario">
          <Share2 className="size-4" /> Exportar
        </button>
        <button type="button" onClick={imprimir} className="boton-primario">
          <Printer className="size-4" /> Imprimir
        </button>
      </div>

      <div className="mb-4 rounded-2xl border border-slate-700/30 bg-slate-900/50 p-4">
        <div className="mb-2 flex items-center gap-2 text-sm text-slate-400">
          <Store className="size-4" />
          Supermercado sugerido
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {supermercados.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setSupermercadoId(s.id)}
              className={`boton-tactil ${
                s.id === supermercadoId
                  ? "bg-emerald-600 text-white"
                  : "border border-slate-700/50 bg-slate-800/60 text-slate-300"
              }`}
            >
              {s.nombre}
              {s.predeterminado && (
                <span className="ml-1 text-[10px] opacity-80">★</span>
              )}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setModalSuper(true)}
            className="boton-secundario"
          >
            <Settings2 className="size-4" /> Administrar
          </button>
        </div>
        {supermercadoActivo && (
          <p className="mt-2 text-xs text-slate-500">
            Se usará <span className="text-emerald-400">{supermercadoActivo.nombre}</span>{" "}
            para nuevas compras y registros de ticket.
          </p>
        )}
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
      {!error && entradas === null && <Cargando />}
      {entradas !== null && entradas.length === 0 && (
        <p className="text-sm text-slate-500">La lista está vacía.</p>
      )}

      <div className="solo-print space-y-4">
        {porCategoria.map(([categoriaId, items]) => {
          const c = datosCategoria(categorias, categoriaId);
          return (
            <section
              key={categoriaId}
              aria-label={`Pasillo ${c.nombre}`}
              className="tarjeta-bento"
              style={{ borderColor: `${c.color}30` }}
            >
              <div className="mb-3 flex items-center gap-2">
                <span className="text-lg">{c.icono}</span>
                <h3
                  className="text-sm font-semibold uppercase tracking-wide"
                  style={{ color: c.color }}
                >
                  {c.nombre}
                </h3>
                <span
                  className="rounded-full px-2 py-0.5 text-xs"
                  style={{ backgroundColor: `${c.color}15`, color: c.color }}
                >
                  pasillo
                </span>
              </div>
              <ul className="space-y-1">
                {items.map((entrada) => (
                  <li key={entrada.item_id}>
                    <div className="flex min-h-11 items-center gap-2 rounded-xl px-2 transition-colors hover:bg-slate-800/40">
                      <input
                        type="checkbox"
                        checked={entrada.comprado}
                        onChange={() => alternar(entrada)}
                        className="size-6 shrink-0 accent-emerald-600"
                      />
                      <span
                        className={`flex-1 ${
                          entrada.comprado
                            ? "text-slate-500 line-through"
                            : "text-slate-200"
                        }`}
                      >
                        {entrada.nombre}
                      </span>
                      {entrada.cantidad !== null && (
                        <span className="shrink-0 text-sm text-slate-500">
                          {formatearCantidad(entrada.cantidad, entrada.unidad)}
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => setEditando(entrada)}
                        aria-label="Editar entrada"
                        className="boton-secundario size-9 p-0"
                      >
                        <Edit2 className="size-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => borrar(entrada)}
                        aria-label="Borrar entrada"
                        className="boton-peligro size-9 p-0"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>

      {modalSuper && (
        <ModalSupermercados
          lista={supermercados}
          onCerrar={() => setModalSuper(false)}
          onCambio={(nueva) => {
            setSupermercados(nueva);
            const pred = nueva.find((s) => s.predeterminado);
            if (pred && !supermercadoId) setSupermercadoId(pred.id);
          }}
        />
      )}

      {editando && (
        <ModalEditarEntrada
          entrada={editando}
          categorias={categorias}
          onCerrar={() => setEditando(null)}
          onGuardar={guardarEdicion}
        />
      )}
    </div>
  );
}

function ModalEditarEntrada({
  entrada,
  categorias,
  onCerrar,
  onGuardar,
}: {
  entrada: EntradaListaCompra;
  categorias: Categoria[];
  onCerrar: () => void;
  onGuardar: (cambios: {
    cantidad?: number;
    unidad?: string;
    categoria?: string;
  }) => void;
}) {
  const [cantidad, setCantidad] = useState(entrada.cantidad ?? 1);
  const [unidad, setUnidad] = useState(entrada.unidad ?? "unidades");
  const [categoria, setCategoria] = useState(entrada.categoria ?? CATEGORIA_GENERAL);

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
          <h3 className="text-lg font-semibold text-slate-100">Editar ítem</h3>
          <button type="button" onClick={onCerrar} className="boton-secundario">
            <X className="size-4" />
          </button>
        </div>
        <p className="mb-4 text-sm text-slate-400">{entrada.nombre}</p>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-300">
              Cantidad
            </label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={cantidad}
              onChange={(ev) => setCantidad(Number(ev.target.value))}
              className="input-premium"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Unidad
              </label>
              <input
                type="text"
                value={unidad}
                onChange={(ev) => setUnidad(ev.target.value)}
                placeholder="unidades"
                className="input-premium"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Categoría
              </label>
              <select
                value={categoria}
                onChange={(ev) => setCategoria(ev.target.value)}
                className="input-premium"
              >
                <option value={CATEGORIA_GENERAL}>General</option>
                {categorias.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.icono} {c.nombre}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <button
            type="button"
            onClick={() =>
              onGuardar({
                cantidad,
                unidad: unidad.trim() || undefined,
                categoria: categoria.trim() || undefined,
              })
            }
            className="boton-primario w-full justify-center"
          >
            <Check className="size-4" /> Guardar cambios
          </button>
        </div>
      </div>
    </div>
  );
}

function ModalSupermercados({
  lista,
  onCerrar,
  onCambio,
}: {
  lista: Supermercado[];
  onCerrar: () => void;
  onCambio: (lista: Supermercado[]) => void;
}) {
  const [items, setItems] = useState(lista);
  const [nuevo, setNuevo] = useState("");
  const [editando, setEditando] = useState<Supermercado | null>(null);
  const [cargando, setCargando] = useState(false);

  useEffect(() => setItems(lista), [lista]);

  const refrescar = async () => {
    const actualizados = await api.getSupermercados();
    setItems(actualizados);
    onCambio(actualizados);
  };

  const crear = async () => {
    if (!nuevo.trim()) return;
    setCargando(true);
    try {
      await api.crearSupermercado(nuevo.trim());
      setNuevo("");
      await refrescar();
    } finally {
      setCargando(false);
    }
  };

  const actualizar = async (id: string, nombre: string) => {
    setCargando(true);
    try {
      await api.actualizarSupermercado(id, { nombre: nombre.trim() });
      setEditando(null);
      await refrescar();
    } finally {
      setCargando(false);
    }
  };

  const eliminar = async (id: string) => {
    setCargando(true);
    try {
      await api.borrarSupermercado(id);
      await refrescar();
    } finally {
      setCargando(false);
    }
  };

  const marcarPredeterminado = async (id: string) => {
    setCargando(true);
    try {
      await api.actualizarSupermercado(id, { predeterminado: true });
      await refrescar();
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
        className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-3xl border border-slate-700/30 bg-slate-900/90 p-6 shadow-2xl"
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-slate-100">
            Administrar supermercados
          </h3>
          <button type="button" onClick={onCerrar} className="boton-secundario">
            <X className="size-4" />
          </button>
        </div>

        <div className="mb-4 flex gap-2">
          <input
            type="text"
            value={nuevo}
            onChange={(ev) => setNuevo(ev.target.value)}
            onKeyDown={(ev) => ev.key === "Enter" && crear()}
            placeholder="Nuevo supermercado"
            className="input-premium flex-1"
          />
          <button
            type="button"
            onClick={crear}
            disabled={cargando || !nuevo.trim()}
            className="boton-primario"
          >
            <Plus className="size-4" />
          </button>
        </div>

        <ul className="space-y-2">
          {items.map((s) => (
            <li
              key={s.id}
              className="flex items-center gap-2 rounded-xl border border-slate-700/30 bg-slate-800/40 p-3"
            >
              {editando?.id === s.id ? (
                <>
                  <input
                    type="text"
                    defaultValue={s.nombre}
                    onKeyDown={(ev) =>
                      ev.key === "Enter" &&
                      actualizar(s.id, ev.currentTarget.value)
                    }
                    className="input-premium flex-1"
                    autoFocus
                  />
                  <button
                    type="button"
                    onClick={(ev) =>
                      actualizar(
                        s.id,
                        ev.currentTarget
                          .closest("li")
                          ?.querySelector("input")?.value ?? s.nombre,
                      )
                    }
                    className="boton-primario size-9 p-0"
                  >
                    <Check className="size-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditando(null)}
                    className="boton-secundario size-9 p-0"
                  >
                    <X className="size-4" />
                  </button>
                </>
              ) : (
                <>
                  <span className="flex-1 text-sm text-slate-200">
                    {s.nombre}
                    {s.predeterminado && (
                      <span className="ml-2 text-[10px] text-emerald-400">
                        predeterminado
                      </span>
                    )}
                  </span>
                  {!s.predeterminado && (
                    <button
                      type="button"
                      onClick={() => marcarPredeterminado(s.id)}
                      title="Marcar como predeterminado"
                      className="boton-secundario size-9 p-0"
                    >
                      <CheckCircle2 className="size-4" />
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setEditando(s)}
                    className="boton-secundario size-9 p-0"
                  >
                    <Edit2 className="size-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => eliminar(s.id)}
                    className="boton-peligro size-9 p-0"
                  >
                    <Trash2 className="size-4" />
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
        {items.length === 0 && (
          <p className="py-4 text-center text-sm text-slate-500">
            No hay supermercados registrados.
          </p>
        )}
        {cargando && (
          <div className="mt-4 flex justify-center">
            <Loader2 className="size-6 animate-spin text-emerald-500" />
          </div>
        )}
      </div>
    </div>
  );
}
