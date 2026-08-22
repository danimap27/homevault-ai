"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ChefHat,
  Clock,
  Edit2,
  Flame,
  Loader2,
  Plus,
  Trash2,
  Utensils,
  X,
} from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import type {
  CategoriaReceta,
  CocinarRecetaResultado,
  Ingrediente,
  Receta,
  RecetaPosible,
  Unidad,
} from "@/lib/types";
import { semanaISOActual } from "@/lib/utils";
import { Cargando, ErrorWidget } from "@/components/estado-async";

const CATEGORIAS: { id: CategoriaReceta; nombre: string }[] = [
  { id: "desayuno", nombre: "Desayuno" },
  { id: "comida", nombre: "Comida" },
  { id: "cena", nombre: "Cena" },
  { id: "snack", nombre: "Snack" },
];

const UNIDADES: Unidad[] = [
  "litros",
  "kg",
  "gramos",
  "unidades",
  "pastillas",
  "dosis",
];

const DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
const TOMAS = ["comida", "cena"];

export default function RecetasPage() {
  const [recetas, setRecetas] = useState<Receta[] | null>(null);
  const [posibles, setPosibles] = useState<RecetaPosible[] | null>(null);
  const [cargandoPosibles, setCargandoPosibles] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [modalRecetaAbierto, setModalRecetaAbierto] = useState(false);
  const [recetaEdicion, setRecetaEdicion] = useState<Receta | null>(null);
  const [confirmarBorrado, setConfirmarBorrado] = useState<Receta | null>(null);
  const [recetaCocinar, setRecetaCocinar] = useState<Receta | null>(null);
  const [recetaPlanificar, setRecetaPlanificar] = useState<Receta | null>(null);
  const [resultadoCocinar, setResultadoCocinar] = useState<CocinarRecetaResultado | null>(null);
  const [resultadoPlanificar, setResultadoPlanificar] = useState<CocinarRecetaResultado | null>(null);

  const cargar = useCallback(() => {
    setError(null);
    api
      .getRecetas()
      .then(setRecetas)
      .catch((err) =>
        setError(
          err instanceof ErrorApi
            ? `Error ${err.status}: ${err.message}`
            : "API no disponible",
        ),
      );
  }, []);

  useEffect(cargar, [cargar]);

  const cargarPosibles = async () => {
    setCargandoPosibles(true);
    try {
      const data = await api.getRecetasPosibles();
      setPosibles(
        data.sort((a, b) => {
          if (a.posible_completa && !b.posible_completa) return -1;
          if (!a.posible_completa && b.posible_completa) return 1;
          return b.score - a.score;
        }),
      );
    } catch (err) {
      setAviso(
        err instanceof ErrorApi
          ? `No se pudieron cargar recetas posibles: ${err.message}`
          : "No se pudieron cargar recetas posibles",
      );
    } finally {
      setCargandoPosibles(false);
    }
  };

  const borrar = async (receta: Receta) => {
    try {
      await api.borrarReceta(receta.id);
      setAviso(`Receta "${receta.titulo}" eliminada`);
      setConfirmarBorrado(null);
      cargar();
    } catch (err) {
      setAviso(
        err instanceof ErrorApi ? err.message : "No se pudo borrar la receta",
      );
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-slate-100">Recetas del vault</h2>
        <button
          type="button"
          onClick={() => setModalRecetaAbierto(true)}
          className="boton-primario"
        >
          <Plus className="size-4" /> Nueva receta
        </button>
      </div>

      {aviso && (
        <p
          className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200"
          role="status"
        >
          {aviso}
        </p>
      )}
      {error && <ErrorWidget mensaje={error} />}
      {!error && recetas === null && <Cargando />}

      {recetas !== null && recetas.length === 0 && (
        <p className="text-sm text-slate-500">No hay recetas guardadas.</p>
      )}

      {recetas !== null && recetas.length > 0 && (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {recetas.map((receta) => (
            <li key={receta.id} className="tarjeta-bento">
              <div className="mb-2 flex items-start justify-between gap-2">
                <h3 className="min-w-0 font-semibold leading-tight text-slate-100">
                  {receta.titulo}
                </h3>
                <div className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => setRecetaEdicion(receta)}
                    className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-100"
                    aria-label="Editar receta"
                  >
                    <Edit2 className="size-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmarBorrado(receta)}
                    className="rounded-lg p-2 text-rose-400 transition-colors hover:bg-rose-950/30"
                    aria-label="Borrar receta"
                  >
                    <Trash2 className="size-4" />
                  </button>
                </div>
              </div>

              <div className="mb-3 flex flex-wrap gap-1.5 text-xs">
                <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-violet-300">
                  {CATEGORIAS.find((c) => c.id === receta.categoria)?.nombre ?? receta.categoria}
                </span>
                <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-sky-300">
                  <Clock className="mr-1 inline size-3" />
                  {receta.tiempo_minutos} min
                </span>
                <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-emerald-300">
                  {receta.raciones} raciones
                </span>
                {receta.calorias_racion && (
                  <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-amber-300">
                    {receta.calorias_racion} kcal/ración
                  </span>
                )}
              </div>

              <p className="mb-3 text-sm text-slate-400">
                {receta.ingredientes.length} ingrediente
                {receta.ingredientes.length === 1 ? "" : "s"}
                {receta.instrucciones ? " · con instrucciones" : ""}
              </p>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setRecetaCocinar(receta)}
                  className="boton-primario flex-1"
                >
                  <Flame className="size-4" /> Cocinar
                </button>
                <button
                  type="button"
                  onClick={() => setRecetaPlanificar(receta)}
                  className="boton-secundario flex-1"
                >
                  <Utensils className="size-4" /> Planificar
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <section className="tarjeta-bento">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ChefHat className="size-5 text-emerald-400" />
            <h2 className="text-base font-semibold text-slate-100">¿Qué puedo cocinar?</h2>
          </div>
          <button
            type="button"
            onClick={cargarPosibles}
            disabled={cargandoPosibles}
            className="boton-secundario"
          >
            {cargandoPosibles ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <>Consultar</>
            )}
          </button>
        </div>

        {posibles === null && !cargandoPosibles && (
          <p className="text-sm text-slate-500">
            Pulsa "Consultar" para ver qué recetas puedes hacer con el inventario actual.
          </p>
        )}

        {cargandoPosibles && <Cargando texto="Analizando inventario…" />}

        {posibles !== null && posibles.length === 0 && (
          <p className="text-sm text-slate-500">
            No hay recetas que se puedan hacer con el stock actual.
          </p>
        )}

        {posibles !== null && posibles.length > 0 && (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {posibles.map(({ receta, posible_completa, faltantes, score }) => (
              <li
                key={receta.id}
                className={`rounded-2xl border p-4 ${
                  posible_completa
                    ? "border-emerald-500/30 bg-emerald-500/10"
                    : "border-amber-500/30 bg-amber-500/10"
                }`}
              >
                <div className="mb-2 flex items-start justify-between gap-2">
                  <h3 className="font-semibold text-slate-100">{receta.titulo}</h3>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${
                      posible_completa
                        ? "bg-emerald-500/20 text-emerald-200"
                        : "bg-amber-500/20 text-amber-200"
                    }`}
                  >
                    {Math.round(score * 100)}%
                  </span>
                </div>

                <p className="mb-2 text-xs text-slate-400">
                  {receta.tiempo_minutos} min · {receta.raciones} raciones
                </p>

                {!posible_completa && faltantes.length > 0 && (
                  <div className="mb-3">
                    <p className="mb-1 text-xs font-medium text-amber-300">Faltantes:</p>
                    <ul className="space-y-0.5 text-xs text-slate-300">
                      {faltantes.map((f, i) => (
                        <li key={i}>
                          {f.nombre}: {f.cantidad_necesaria - f.cantidad_disponible} {f.unidad}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setRecetaCocinar(receta)}
                    className="boton-primario flex-1"
                  >
                    <Flame className="size-4" /> Cocinar
                  </button>
                  <button
                    type="button"
                    onClick={() => setRecetaPlanificar(receta)}
                    className="boton-secundario flex-1"
                  >
                    Planificar
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {(modalRecetaAbierto || recetaEdicion) && (
        <ModalReceta
          receta={recetaEdicion}
          onCerrar={() => {
            setModalRecetaAbierto(false);
            setRecetaEdicion(null);
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
            <h3 className="mb-2 text-lg font-semibold text-slate-100">¿Borrar receta?</h3>
            <p className="mb-4 text-sm text-slate-400">
              Se eliminará permanentemente <strong>{confirmarBorrado.titulo}</strong>.
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

      {recetaCocinar && (
        <ModalCocinar
          receta={recetaCocinar}
          onCerrar={() => {
            setRecetaCocinar(null);
            setResultadoCocinar(null);
          }}
          onExito={(mensaje, resultado) => {
            setAviso(mensaje);
            if (resultado) setResultadoCocinar(resultado);
          }}
        />
      )}

      {resultadoCocinar && (
        <ModalResultado
          titulo="Resultado de cocinar"
          resultado={resultadoCocinar}
          onCerrar={() => setResultadoCocinar(null)}
        />
      )}

      {recetaPlanificar && (
        <ModalPlanificar
          receta={recetaPlanificar}
          onCerrar={() => {
            setRecetaPlanificar(null);
            setResultadoPlanificar(null);
          }}
          onExito={(mensaje, resultado) => {
            setAviso(mensaje);
            if (resultado) setResultadoPlanificar(resultado);
          }}
        />
      )}

      {resultadoPlanificar && (
        <ModalResultado
          titulo="Faltantes añadidos a la lista de la compra"
          resultado={resultadoPlanificar}
          onCerrar={() => setResultadoPlanificar(null)}
        />
      )}
    </div>
  );
}

function ModalReceta({
  receta,
  onCerrar,
  onExito,
}: {
  receta: Receta | null;
  onCerrar: () => void;
  onExito: (mensaje: string) => void;
}) {
  const editando = receta !== null;
  const [titulo, setTitulo] = useState(receta?.titulo ?? "");
  const [categoria, setCategoria] = useState<CategoriaReceta>(
    receta?.categoria ?? "comida",
  );
  const [tiempo, setTiempo] = useState(receta?.tiempo_minutos ?? 30);
  const [raciones, setRaciones] = useState(receta?.raciones ?? 2);
  const [calorias, setCalorias] = useState(receta?.calorias_racion ?? "");
  const [ingredientes, setIngredientes] = useState<Ingrediente[]>(
    receta?.ingredientes?.length
      ? receta.ingredientes
      : [{ item_id: null, nombre: "", cantidad: 0, unidad: "unidades" }],
  );
  const [instrucciones, setInstrucciones] = useState(receta?.instrucciones ?? "");
  const [tags, setTags] = useState(receta?.tags.join(", ") ?? "");
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const agregarIngrediente = () => {
    setIngredientes((prev) => [
      ...prev,
      { item_id: null, nombre: "", cantidad: 0, unidad: "unidades" },
    ]);
  };

  const actualizarIngrediente = (idx: number, cambios: Partial<Ingrediente>) => {
    setIngredientes((prev) =>
      prev.map((ing, i) => (i === idx ? { ...ing, ...cambios } : ing)),
    );
  };

  const eliminarIngrediente = (idx: number) => {
    setIngredientes((prev) => prev.filter((_, i) => i !== idx));
  };

  const enviar = async () => {
    if (!titulo.trim()) {
      setError("El título es obligatorio");
      return;
    }
    const validos = ingredientes.filter((i) => i.nombre.trim() && i.cantidad > 0);
    if (validos.length === 0) {
      setError("Añade al menos un ingrediente válido");
      return;
    }
    setCargando(true);
    setError(null);
    try {
      const payload = {
        titulo: titulo.trim(),
        categoria,
        tiempo_minutos: Number(tiempo) || 30,
        raciones: Number(raciones) || 2,
        calorias_racion: calorias === "" ? null : Number(calorias),
        ingredientes: validos,
        instrucciones: instrucciones.trim() || null,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      };
      if (editando) {
        await api.actualizarReceta(receta.id, payload);
        onExito(`Receta "${payload.titulo}" actualizada`);
      } else {
        await api.crearReceta(payload);
        onExito(`Receta "${payload.titulo}" creada`);
      }
      onCerrar();
    } catch (err) {
      setError(
        err instanceof ErrorApi ? err.message : "No se pudo guardar la receta",
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
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-3xl border border-slate-700/30 bg-slate-900/90 p-6 shadow-2xl"
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-slate-100">
            {editando ? "Editar receta" : "Nueva receta"}
          </h3>
          <button type="button" onClick={onCerrar} className="boton-secundario">
            <X className="size-4" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-300">Título</label>
            <input
              type="text"
              value={titulo}
              onChange={(ev) => setTitulo(ev.target.value)}
              className="input-premium"
              placeholder="Ej. Tortilla de patatas"
            />
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Categoría
              </label>
              <select
                value={categoria}
                onChange={(ev) => setCategoria(ev.target.value as CategoriaReceta)}
                className="input-premium"
              >
                {CATEGORIAS.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nombre}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Tiempo (min)
              </label>
              <input
                type="number"
                min="1"
                value={tiempo}
                onChange={(ev) => setTiempo(Number(ev.target.value))}
                className="input-premium"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Raciones
              </label>
              <input
                type="number"
                min="1"
                value={raciones}
                onChange={(ev) => setRaciones(Number(ev.target.value))}
                className="input-premium"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Kcal/ración
              </label>
              <input
                type="number"
                min="0"
                value={calorias}
                onChange={(ev) =>
                  setCalorias(ev.target.value === "" ? "" : Number(ev.target.value))
                }
                className="input-premium"
                placeholder="Opcional"
              />
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="text-sm font-medium text-slate-300">Ingredientes</label>
              <button
                type="button"
                onClick={agregarIngrediente}
                className="text-xs text-emerald-400 hover:text-emerald-300"
              >
                + Añadir ingrediente
              </button>
            </div>
            <div className="space-y-2">
              {ingredientes.map((ing, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-2">
                  <input
                    type="text"
                    value={ing.nombre}
                    onChange={(ev) =>
                      actualizarIngrediente(idx, { nombre: ev.target.value })
                    }
                    placeholder="Nombre"
                    className="col-span-5 input-premium"
                  />
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={ing.cantidad}
                    onChange={(ev) =>
                      actualizarIngrediente(idx, { cantidad: Number(ev.target.value) })
                    }
                    placeholder="Cantidad"
                    className="col-span-3 input-premium"
                  />
                  <select
                    value={ing.unidad}
                    onChange={(ev) =>
                      actualizarIngrediente(idx, { unidad: ev.target.value })
                    }
                    className="col-span-3 input-premium"
                  >
                    {UNIDADES.map((u) => (
                      <option key={u} value={u}>
                        {u}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => eliminarIngrediente(idx)}
                    className="col-span-1 flex items-center justify-center rounded-xl text-rose-400 hover:bg-rose-950/30"
                    aria-label="Eliminar ingrediente"
                  >
                    <X className="size-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-300">
              Instrucciones (Markdown)
            </label>
            <textarea
              value={instrucciones}
              onChange={(ev) => setInstrucciones(ev.target.value)}
              rows={5}
              className="input-premium"
              placeholder="1. Pelar las patatas..."
            />
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
              placeholder="vegetariano, rápido, invierno"
            />
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
              <>Guardar receta</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function ModalCocinar({
  receta,
  onCerrar,
  onExito,
}: {
  receta: Receta;
  onCerrar: () => void;
  onExito: (mensaje: string, resultado?: CocinarRecetaResultado) => void;
}) {
  const [raciones, setRaciones] = useState(receta.raciones);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enviar = async () => {
    setCargando(true);
    setError(null);
    try {
      const res = await api.cocinarReceta(receta.id, { raciones });
      const faltan = res.faltantes.length;
      const partes = [
        `Cocinada "${receta.titulo}" para ${res.raciones} ración${
          res.raciones === 1 ? "" : "es"
        }`,
      ];
      if (faltan > 0) partes.push(`${faltan} ingrediente${faltan === 1 ? "" : "s"} faltante${faltan === 1 ? "" : "s"}`);
      onExito(partes.join(" · "), res);
      onCerrar();
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo cocinar la receta");
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
        className="w-full max-w-sm rounded-3xl border border-slate-700/30 bg-slate-900/90 p-6 shadow-2xl"
        onClick={(ev) => ev.stopPropagation()}
      >
        <h3 className="mb-2 text-lg font-semibold text-slate-100">Cocinar receta</h3>
        <p className="mb-4 text-sm text-slate-400">{receta.titulo}</p>

        <div className="mb-4">
          <label className="mb-1 block text-sm font-medium text-slate-300">
            Raciones
          </label>
          <input
            type="number"
            min="1"
            value={raciones}
            onChange={(ev) => setRaciones(Number(ev.target.value))}
            className="input-premium"
          />
        </div>

        {error && (
          <p className="mb-3 rounded-xl border border-rose-500/30 bg-rose-500/10 p-2 text-sm text-rose-200">
            {error}
          </p>
        )}

        <div className="flex gap-2">
          <button type="button" onClick={onCerrar} className="boton-secundario flex-1">
            Cancelar
          </button>
          <button
            type="button"
            onClick={enviar}
            disabled={cargando}
            className="boton-primario flex-1 justify-center"
          >
            {cargando ? <Loader2 className="size-4 animate-spin" /> : <>Cocinar ahora</>}
          </button>
        </div>
      </div>
    </div>
  );
}

function ModalPlanificar({
  receta,
  onCerrar,
  onExito,
}: {
  receta: Receta;
  onCerrar: () => void;
  onExito: (mensaje: string, resultado?: CocinarRecetaResultado) => void;
}) {
  const [semana, setSemana] = useState(semanaISOActual());
  const [dia, setDia] = useState(DIAS[0]);
  const [toma, setToma] = useState(TOMAS[0]);
  const [raciones, setRaciones] = useState(receta.raciones);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enviar = async () => {
    setCargando(true);
    setError(null);
    try {
      const res = await api.asignarPlan({
        semana_iso: semana,
        dia,
        toma,
        receta_id: receta.id,
        raciones,
      });
      const faltan = res.anadidos_a_lista_compra.length;
      const partes = [
        `"${receta.titulo}" planificado para ${dia} ${toma} (${semana})`,
      ];
      if (faltan > 0)
        partes.push(`${faltan} faltante${faltan === 1 ? "" : "s"} añadido${faltan === 1 ? "" : "s"} a la compra`);
      onExito(partes.join(" · "), res);
      onCerrar();
    } catch (err) {
      setError(err instanceof ErrorApi ? err.message : "No se pudo asignar la receta");
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
        className="w-full max-w-sm rounded-3xl border border-slate-700/30 bg-slate-900/90 p-6 shadow-2xl"
        onClick={(ev) => ev.stopPropagation()}
      >
        <h3 className="mb-2 text-lg font-semibold text-slate-100">Planificar receta</h3>
        <p className="mb-4 text-sm text-slate-400">{receta.titulo}</p>

        <div className="mb-4 space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-300">
              Semana ISO
            </label>
            <input
              type="text"
              value={semana}
              onChange={(ev) => setSemana(ev.target.value)}
              placeholder="2026-W34"
              className="input-premium"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">Día</label>
              <select
                value={dia}
                onChange={(ev) => setDia(ev.target.value)}
                className="input-premium"
              >
                {DIAS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">Toma</label>
              <select
                value={toma}
                onChange={(ev) => setToma(ev.target.value)}
                className="input-premium"
              >
                {TOMAS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-300">
              Raciones
            </label>
            <input
              type="number"
              min="1"
              value={raciones}
              onChange={(ev) => setRaciones(Number(ev.target.value))}
              className="input-premium"
            />
          </div>
        </div>

        {error && (
          <p className="mb-3 rounded-xl border border-rose-500/30 bg-rose-500/10 p-2 text-sm text-rose-200">
            {error}
          </p>
        )}

        <div className="flex gap-2">
          <button type="button" onClick={onCerrar} className="boton-secundario flex-1">
            Cancelar
          </button>
          <button
            type="button"
            onClick={enviar}
            disabled={cargando}
            className="boton-primario flex-1 justify-center"
          >
            {cargando ? <Loader2 className="size-4 animate-spin" /> : <>Asignar</>}
          </button>
        </div>
      </div>
    </div>
  );
}

function ModalResultado({
  titulo,
  resultado,
  onCerrar,
}: {
  titulo: string;
  resultado: CocinarRecetaResultado;
  onCerrar: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
      onClick={onCerrar}
    >
      <div
        className="max-h-[80vh] w-full max-w-md overflow-y-auto rounded-3xl border border-slate-700/30 bg-slate-900/90 p-6 shadow-2xl"
        onClick={(ev) => ev.stopPropagation()}
      >
        <h3 className="mb-4 text-lg font-semibold text-slate-100">{titulo}</h3>

        {resultado.consumidos.length > 0 && (
          <div className="mb-4">
            <h4 className="mb-2 text-sm font-medium text-emerald-300">Consumido</h4>
            <ul className="space-y-1 text-sm text-slate-300">
              {resultado.consumidos.map((c, i) => (
                <li key={i}>
                  {c.nombre}: {c.cantidad} {c.unidad}
                </li>
              ))}
            </ul>
          </div>
        )}

        {resultado.faltantes.length > 0 && (
          <div className="mb-4">
            <h4 className="mb-2 text-sm font-medium text-amber-300">Faltantes</h4>
            <ul className="space-y-1 text-sm text-slate-300">
              {resultado.faltantes.map((f, i) => (
                <li key={i}>
                  {f.nombre}: falta{" "}
                  {Math.max(0, f.cantidad_necesaria - f.cantidad_disponible)} {f.unidad}
                </li>
              ))}
            </ul>
          </div>
        )}

        {resultado.anadidos_a_lista_compra.length > 0 && (
          <div className="mb-4">
            <h4 className="mb-2 text-sm font-medium text-violet-300">
              Añadidos a la lista de la compra
            </h4>
            <ul className="space-y-1 text-sm text-slate-300">
              {resultado.anadidos_a_lista_compra.map((a, i) => (
                <li key={i}>
                  {a.nombre}: {a.cantidad} {a.unidad}
                </li>
              ))}
            </ul>
          </div>
        )}

        <button type="button" onClick={onCerrar} className="boton-primario w-full">
          Cerrar
        </button>
      </div>
    </div>
  );
}
