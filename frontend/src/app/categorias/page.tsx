"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Check,
  FolderOpen,
  Loader2,
  Pencil,
  Plus,
  Tags,
  Trash2,
  X,
} from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import type { Categoria, Consumible } from "@/lib/types";
import { Cargando, ErrorWidget } from "@/components/estado-async";

const UBICACIONES_DEFAULT = [
  { id: "nevera", nombre: "Nevera" },
  { id: "congelador", nombre: "Congelador" },
  { id: "despensa", nombre: "Despensa" },
  { id: "bano", nombre: "Baño" },
  { id: "trastero", nombre: "Trastero" },
];

function categoriaVacia(): Categoria {
  return {
    id: "",
    nombre: "",
    color: "#10b981",
    icono: "📦",
    ubicacion_default: null,
    orden: 0,
  };
}

export default function CategoriasPage() {
  const [categorias, setCategorias] = useState<Categoria[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [modalAbierto, setModalAbierto] = useState(false);
  const [editando, setEditando] = useState<Categoria | null>(null);
  const [formulario, setFormulario] = useState<Categoria>(categoriaVacia());
  const [cargando, setCargando] = useState(false);

  const [borrando, setBorrando] = useState<Categoria | null>(null);
  const [reemplazo, setReemplazo] = useState<string>("");
  const [itemsBloqueando, setItemsBloqueando] = useState<Consumible[]>([]);

  const cargar = useCallback(() => {
    setError(null);
    api
      .getCategorias()
      .then((lista) => setCategorias(lista.sort((a, b) => a.orden - b.orden)))
      .catch((err) =>
        setError(
          err instanceof ErrorApi
            ? `Error ${err.status}: ${err.message}`
            : "API no disponible",
        ),
      );
  }, []);

  useEffect(cargar, [cargar]);

  const abrirNuevo = () => {
    setEditando(null);
    setFormulario(categoriaVacia());
    setModalAbierto(true);
  };

  const abrirEditar = (categoria: Categoria) => {
    setEditando(categoria);
    setFormulario({ ...categoria });
    setModalAbierto(true);
  };

  const guardar = async () => {
    if (!formulario.id.trim() || !formulario.nombre.trim()) {
      setAviso("El identificador y el nombre son obligatorios");
      return;
    }
    setCargando(true);
    setAviso(null);
    try {
      const payload: Categoria = {
        ...formulario,
        id: formulario.id.trim(),
        nombre: formulario.nombre.trim(),
        icono: formulario.icono.trim() || "📦",
      };
      if (editando) {
        await api.actualizarCategoria(editando.id, payload);
        setAviso(`Categoría "${payload.nombre}" actualizada`);
      } else {
        await api.crearCategoria(payload);
        setAviso(`Categoría "${payload.nombre}" creada`);
      }
      setModalAbierto(false);
      cargar();
    } catch (err) {
      setAviso(
        err instanceof ErrorApi ? err.message : "No se pudo guardar la categoría",
      );
    } finally {
      setCargando(false);
    }
  };

  const iniciarBorrado = async (categoria: Categoria) => {
    setAviso(null);
    setReemplazo("");
    setItemsBloqueando([]);
    try {
      await api.borrarCategoria(categoria.id);
      setAviso(`Categoría "${categoria.nombre}" eliminada`);
      cargar();
    } catch (err) {
      if (
        err instanceof ErrorApi &&
        err.status === 409 &&
        Array.isArray((err.data as { items?: unknown })?.items)
      ) {
        setBorrando(categoria);
        setItemsBloqueando(
          (err.data as { items: Consumible[] }).items,
        );
      } else {
        setAviso(
          err instanceof ErrorApi
            ? err.message
            : "No se pudo eliminar la categoría",
        );
      }
    }
  };

  const confirmarBorradoConReemplazo = async () => {
    if (!borrando || !reemplazo) return;
    setCargando(true);
    try {
      await api.borrarCategoria(borrando.id, reemplazo);
      setAviso(`Categoría "${borrando.nombre}" eliminada y reasignada`);
      setBorrando(null);
      setReemplazo("");
      setItemsBloqueando([]);
      cargar();
    } catch (err) {
      setAviso(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo eliminar la categoría",
      );
    } finally {
      setCargando(false);
    }
  };

  const categoriasSinLaActiva = useMemo(
    () => categorias?.filter((c) => c.id !== borrando?.id) ?? [],
    [categorias, borrando],
  );

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h2 className="mr-auto flex items-center gap-2 text-lg font-semibold text-slate-100">
          <Tags className="size-5" /> Categorías
        </h2>
        <button type="button" onClick={abrirNuevo} className="boton-primario">
          <Plus className="size-4" /> Nueva categoría
        </button>
      </div>

      {aviso && (
        <p
          className={`mb-4 rounded-xl border p-3 text-sm ${
            aviso.includes("Error") || aviso.includes("No se pudo")
              ? "border-rose-500/30 bg-rose-500/10 text-rose-200"
              : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
          }`}
          role="status"
        >
          {aviso}
        </p>
      )}
      {error && <ErrorWidget mensaje={error} />}
      {!error && categorias === null && <Cargando />}
      {categorias !== null && categorias.length === 0 && (
        <p className="text-sm text-slate-500">
          No hay categorías personalizadas. Crea la primera para organizar el inventario.
        </p>
      )}

      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {categorias?.map((categoria) => (
          <li
            key={categoria.id}
            className="tarjeta-bento flex items-center gap-4"
            style={{ borderColor: `${categoria.color}40` }}
          >
            <div
              className="flex size-14 shrink-0 items-center justify-center rounded-2xl text-2xl"
              style={{ backgroundColor: `${categoria.color}20`, color: categoria.color }}
            >
              {categoria.icono}
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="truncate font-semibold text-slate-100">
                {categoria.nombre}
              </h3>
              <p className="text-xs text-slate-500">
                {categoria.id} · orden {categoria.orden}
                {categoria.ubicacion_default
                  ? ` · ${categoria.ubicacion_default}`
                  : ""}
              </p>
            </div>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => abrirEditar(categoria)}
                aria-label="Editar categoría"
                className="boton-secundario size-9 p-0"
              >
                <Pencil className="size-4" />
              </button>
              <button
                type="button"
                onClick={() => iniciarBorrado(categoria)}
                aria-label="Eliminar categoría"
                className="boton-peligro size-9 p-0"
              >
                <Trash2 className="size-4" />
              </button>
            </div>
          </li>
        ))}
      </ul>

      {modalAbierto && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
          onClick={() => setModalAbierto(false)}
        >
          <div
            className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-3xl border border-slate-700/30 bg-slate-900/90 p-6 shadow-2xl"
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-slate-100">
                {editando ? "Editar categoría" : "Nueva categoría"}
              </h3>
              <button
                type="button"
                onClick={() => setModalAbierto(false)}
                className="boton-secundario"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-300">
                  Identificador (slug) *
                </label>
                <input
                  type="text"
                  value={formulario.id}
                  onChange={(ev) =>
                    setFormulario({ ...formulario, id: ev.target.value })
                  }
                  disabled={!!editando}
                  placeholder="ej. lacteos"
                  className="input-premium disabled:opacity-50"
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-300">
                  Nombre *
                </label>
                <input
                  type="text"
                  value={formulario.nombre}
                  onChange={(ev) =>
                    setFormulario({ ...formulario, nombre: ev.target.value })
                  }
                  placeholder="Ej. Lácteos"
                  className="input-premium"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-300">
                    Color
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={formulario.color}
                      onChange={(ev) =>
                        setFormulario({ ...formulario, color: ev.target.value })
                      }
                      className="h-11 w-14 cursor-pointer rounded-lg border-0 bg-transparent p-0"
                    />
                    <span className="text-xs text-slate-500">
                      {formulario.color}
                    </span>
                  </div>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-300">
                    Icono (emoji)
                  </label>
                  <input
                    type="text"
                    value={formulario.icono}
                    onChange={(ev) =>
                      setFormulario({ ...formulario, icono: ev.target.value })
                    }
                    placeholder="📦"
                    className="input-premium"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-300">
                    Ubicación por defecto
                  </label>
                  <select
                    value={formulario.ubicacion_default ?? ""}
                    onChange={(ev) =>
                      setFormulario({
                        ...formulario,
                        ubicacion_default: ev.target.value || null,
                      })
                    }
                    className="input-premium"
                  >
                    <option value="">Ninguna</option>
                    {UBICACIONES_DEFAULT.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.nombre}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-300">
                    Orden
                  </label>
                  <input
                    type="number"
                    value={formulario.orden}
                    onChange={(ev) =>
                      setFormulario({
                        ...formulario,
                        orden: Number(ev.target.value),
                      })
                    }
                    className="input-premium"
                  />
                </div>
              </div>

              <button
                type="button"
                onClick={guardar}
                disabled={cargando}
                className="boton-primario w-full justify-center"
              >
                {cargando ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <>
                    <Check className="size-4" /> Guardar categoría
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {borrando && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
          onClick={() => setBorrando(null)}
        >
          <div
            className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-3xl border border-slate-700/30 bg-slate-900/90 p-6 shadow-2xl"
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="mb-4 flex items-center gap-3">
              <div
                className="flex size-10 shrink-0 items-center justify-center rounded-xl"
                style={{
                  backgroundColor: `${borrando.color}20`,
                  color: borrando.color,
                }}
              >
                <FolderOpen className="size-5" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-slate-100">
                  Reasignar ítems
                </h3>
                <p className="text-sm text-slate-400">
                  {borrando.nombre} tiene {itemsBloqueando.length} ítem(s).
                </p>
              </div>
            </div>

            <p className="mb-4 text-sm text-slate-300">
              Elige otra categoría para reasignar los ítems antes de eliminar.
            </p>

            <ul className="mb-4 max-h-40 space-y-1 overflow-y-auto rounded-xl border border-slate-700/30 bg-slate-800/40 p-2 text-xs text-slate-400">
              {itemsBloqueando.map((item) => (
                <li key={item.id} className="truncate">
                  • {item.nombre}
                </li>
              ))}
            </ul>

            <label className="mb-1 block text-sm font-medium text-slate-300">
              Categoría de reemplazo
            </label>
            <select
              value={reemplazo}
              onChange={(ev) => setReemplazo(ev.target.value)}
              className="input-premium mb-4"
            >
              <option value="">Selecciona una categoría</option>
              {categoriasSinLaActiva.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.icono} {c.nombre}
                </option>
              ))}
            </select>

            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setBorrando(null)}
                className="boton-secundario flex-1"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={confirmarBorradoConReemplazo}
                disabled={cargando || !reemplazo}
                className="boton-peligro flex-1"
              >
                {cargando ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <>
                    <Trash2 className="size-4" /> Eliminar y reasignar
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
