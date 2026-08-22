"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Barcode,
  Check,
  Edit2,
  Loader2,
  Package,
  Plus,
  Save,
  Store,
  Trash2,
  X,
} from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import type { Categoria, CategoriaItem, LocalBarcode, Supermercado, Ubicacion, Unidad } from "@/lib/types";
import { Cargando, ErrorWidget } from "@/components/estado-async";

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

function formularioVacio(categoriaDefault: CategoriaItem): LocalBarcode {
  return {
    ean: "",
    nombre: "",
    categoria: categoriaDefault,
    ubicacion: "despensa",
    unidad: "unidades",
    supermercado: null,
    precio_unitario_estimado: null,
    tags: [],
  };
}

export default function BarcodesPage() {
  const [barcodes, setBarcodes] = useState<LocalBarcode[] | null>(null);
  const [supermercados, setSupermercados] = useState<Supermercado[]>([]);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [formulario, setFormulario] = useState<LocalBarcode | null>(null);
  const [cargando, setCargando] = useState(false);

  const categoriaDefault = categorias[0]?.id ?? "";

  const cargar = useCallback(() => {
    setError(null);
    Promise.all([api.getLocalBarcodes(), api.getSupermercados(), api.getCategorias()])
      .then(([lista, supers, cats]) => {
        setBarcodes(lista);
        setSupermercados(supers);
        setCategorias(cats.sort((a, b) => a.orden - b.orden));
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

  const abrirNuevo = (eanInicial = "") => {
    setFormulario({ ...formularioVacio(categoriaDefault), ean: eanInicial });
  };

  const abrirEditar = (barcode: LocalBarcode) => {
    setFormulario({ ...barcode });
  };

  const guardar = async () => {
    if (!formulario) return;
    if (!formulario.ean.trim() || !formulario.nombre.trim()) {
      setAviso("EAN y nombre son obligatorios");
      return;
    }
    setCargando(true);
    setAviso(null);
    try {
      const existe = barcodes?.some((b) => b.ean === formulario.ean.trim());
      const payload: LocalBarcode = {
        ...formulario,
        ean: formulario.ean.trim(),
        nombre: formulario.nombre.trim(),
      };
      if (existe) {
        await api.actualizarLocalBarcode(payload.ean, payload);
        setAviso(`Código ${payload.ean} actualizado`);
      } else {
        await api.crearLocalBarcode(payload);
        setAviso(`Código ${payload.ean} creado`);
      }
      setFormulario(null);
      cargar();
    } catch (err) {
      setAviso(
        err instanceof ErrorApi ? err.message : "No se pudo guardar el código",
      );
    } finally {
      setCargando(false);
    }
  };

  const eliminar = async (ean: string) => {
    if (!confirm(`¿Eliminar el código ${ean}?`)) return;
    setCargando(true);
    try {
      await api.borrarLocalBarcode(ean);
      setAviso(`Código ${ean} eliminado`);
      cargar();
    } catch (err) {
      setAviso(
        err instanceof ErrorApi ? err.message : "No se pudo eliminar el código",
      );
    } finally {
      setCargando(false);
    }
  };

  const nombreSupermercado = (id: string | null) =>
    supermercados.find((s) => s.id === id)?.nombre ?? id ?? "—";

  const nombreCategoria = (id: string) =>
    categorias.find((c) => c.id === id)?.nombre ?? id.replace(/_/g, " ");

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h2 className="mr-auto text-lg font-semibold text-slate-100">
          Códigos de barras locales
        </h2>
        <button
          type="button"
          onClick={() => abrirNuevo()}
          className="boton-primario"
        >
          <Plus className="size-4" /> Añadir
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
      {!error && barcodes === null && <Cargando />}
      {barcodes !== null && barcodes.length === 0 && (
        <p className="text-sm text-slate-500">No hay códigos locales registrados.</p>
      )}

      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {barcodes?.map((b) => (
          <li key={b.ean} className="tarjeta-bento">
            <div className="mb-2 flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="flex size-9 items-center justify-center rounded-xl bg-violet-500/15 text-violet-400">
                  <Barcode className="size-5" />
                </div>
                <div>
                  <h3 className="font-semibold text-slate-100">{b.nombre}</h3>
                  <p className="text-xs text-slate-500">{b.ean}</p>
                </div>
              </div>
              <div className="flex gap-1">
                <button
                  type="button"
                  onClick={() => abrirEditar(b)}
                  aria-label="Editar código"
                  className="boton-secundario size-9 p-0"
                >
                  <Edit2 className="size-4" />
                </button>
                <button
                  type="button"
                  onClick={() => eliminar(b.ean)}
                  aria-label="Eliminar código"
                  className="boton-peligro size-9 p-0"
                >
                  <Trash2 className="size-4" />
                </button>
              </div>
            </div>

            <div className="mb-3 grid grid-cols-2 gap-2 text-xs">
              <span className="rounded-lg bg-slate-800/60 px-2 py-1 text-slate-300">
                <Package className="mr-1 inline size-3" />
                {nombreCategoria(b.categoria)}
              </span>
              <span className="rounded-lg bg-slate-800/60 px-2 py-1 text-slate-300">
                {b.ubicacion}
              </span>
              <span className="rounded-lg bg-slate-800/60 px-2 py-1 text-slate-300">
                {b.unidad}
              </span>
              <span className="rounded-lg bg-slate-800/60 px-2 py-1 text-slate-300">
                {b.precio_unitario_estimado?.toFixed(2) ?? "—"} €
              </span>
              <span className="col-span-2 rounded-lg bg-slate-800/60 px-2 py-1 text-slate-300">
                <Store className="mr-1 inline size-3" />
                {nombreSupermercado(b.supermercado)}
              </span>
            </div>
          </li>
        ))}
      </ul>

      {formulario && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
          onClick={() => setFormulario(null)}
        >
          <div
            className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-3xl border border-slate-700/30 bg-slate-900/90 p-6 shadow-2xl"
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-slate-100">
                {barcodes?.some((b) => b.ean === formulario.ean)
                  ? "Editar código"
                  : "Añadir código"}
              </h3>
              <button
                type="button"
                onClick={() => setFormulario(null)}
                className="boton-secundario"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-300">
                  EAN *
                </label>
                <input
                  type="text"
                  value={formulario.ean}
                  onChange={(ev) =>
                    setFormulario({ ...formulario, ean: ev.target.value })
                  }
                  placeholder="1234567890123"
                  className="input-premium"
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
                  placeholder="Nombre del producto"
                  className="input-premium"
                />
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-300">
                    Categoría
                  </label>
                  <select
                    value={formulario.categoria}
                    onChange={(ev) =>
                      setFormulario({
                        ...formulario,
                        categoria: ev.target.value as CategoriaItem,
                      })
                    }
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
                    value={formulario.ubicacion}
                    onChange={(ev) =>
                      setFormulario({
                        ...formulario,
                        ubicacion: ev.target.value as Ubicacion,
                      })
                    }
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
                    value={formulario.unidad}
                    onChange={(ev) =>
                      setFormulario({
                        ...formulario,
                        unidad: ev.target.value as Unidad,
                      })
                    }
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
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-300">
                    Precio estimado (€)
                  </label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={formulario.precio_unitario_estimado ?? ""}
                    onChange={(ev) =>
                      setFormulario({
                        ...formulario,
                        precio_unitario_estimado:
                          ev.target.value === ""
                            ? null
                            : Number(ev.target.value),
                      })
                    }
                    placeholder="0.00"
                    className="input-premium"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-300">
                    <Store className="mr-1 inline size-4" />
                    Supermercado
                  </label>
                  <select
                    value={formulario.supermercado ?? ""}
                    onChange={(ev) =>
                      setFormulario({
                        ...formulario,
                        supermercado: ev.target.value || null,
                      })
                    }
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
              </div>

              <button
                type="button"
                onClick={guardar}
                disabled={cargando}
                className="boton-primario w-full justify-center"
              >
                {cargando ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : barcodes?.some((b) => b.ean === formulario.ean) ? (
                  <>
                    <Save className="size-4" /> Guardar cambios
                  </>
                ) : (
                  <>
                    <Check className="size-4" /> Crear código
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
