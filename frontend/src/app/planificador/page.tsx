"use client";

import { useCallback, useEffect, useState } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { api, ErrorApi } from "@/lib/api";
import type {
  ComidaPlanificada,
  PlanSemanal,
  Receta,
  SugerenciaRescate,
} from "@/lib/types";
import { semanaISOActual } from "@/lib/utils";
import {
  Cargando,
  EndpointPendiente,
  ErrorWidget,
} from "@/components/estado-async";

const DIAS = [
  "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
] as const;
const TOMAS = ["comida", "cena"] as const;

type SlotId = `${(typeof DIAS)[number]}:${(typeof TOMAS)[number]}`;

/**
 * Planificador semanal: arrastra recetas (dnd-kit, con soporte táctil vía
 * PointerSensor) a los slots día/toma. Si aún no hay plan de la semana en
 * el vault (404), la página arranca con un plan vacío local que se persiste
 * al guardar (PUT /api/planner/current).
 */
export default function PlanificadorPage() {
  const [recetas, setRecetas] = useState<Receta[] | null>(null);
  const [plan, setPlan] = useState<PlanSemanal | null>(null);
  const [pendiente, setPendiente] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [recetaArrastrada, setRecetaArrastrada] = useState<Receta | null>(null);
  const [rescue, setRescue] = useState<SugerenciaRescate[] | null>(null);
  const [batchAbierto, setBatchAbierto] = useState(false);

  // PointerSensor con retraso mínimo: compatible con ratón y pantalla táctil.
  const sensores = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  );

  useEffect(() => {
    const semana = semanaISOActual();
    const planVacio: PlanSemanal = {
      semana_iso: semana,
      fecha_inicio: "",
      fecha_fin: "",
      dias: {},
      batch_cooking_programado: [],
    };

    api
      .getRecetas()
      .then(setRecetas)
      .catch((err) => {
        if (err instanceof ErrorApi && err.status === 404) {
          setPendiente("GET /api/recipes");
          setRecetas([]);
        } else {
          setError("No se pudieron cargar las recetas");
        }
      });

    api
      .getPlanActual()
      .then(setPlan)
      .catch((err) => {
        if (err instanceof ErrorApi && err.status === 404) {
          // Semana sin plan en el vault: se empieza con un plan vacío local.
          setPlan(planVacio);
        } else {
          setError("No se pudo cargar el plan semanal");
        }
      });
  }, []);

  const alEmpezarArrastre = (ev: DragStartEvent) => {
    const receta = (recetas ?? []).find((r) => r.id === ev.active.id);
    setRecetaArrastrada(receta ?? null);
  };

  const alSoltar = (ev: DragEndEvent) => {
    setRecetaArrastrada(null);
    if (!ev.over || !plan) return;
    const [dia, toma] = String(ev.over.id).split(":") as [
      (typeof DIAS)[number],
      (typeof TOMAS)[number],
    ];
    const receta = (recetas ?? []).find((r) => r.id === ev.active.id);
    if (!receta) return;
    setPlan({
      ...plan,
      dias: {
        ...plan.dias,
        [dia]: {
          ...plan.dias[dia],
          [toma]: {
            receta_id: receta.id,
            plato_libre: null,
            raciones: receta.raciones,
            stock_deducido: false,
          } satisfies ComidaPlanificada,
        },
      },
    });
    setAviso(null);
  };

  const limpiarSlot = (slot: SlotId) => {
    if (!plan) return;
    const [dia, toma] = slot.split(":");
    setPlan({
      ...plan,
      dias: {
        ...plan.dias,
        [dia]: {
          ...plan.dias[dia],
          [toma]: {
            receta_id: null,
            plato_libre: null,
            raciones: null,
            stock_deducido: false,
          },
        },
      },
    });
  };

  const guardar = async () => {
    if (!plan) return;
    try {
      const guardado = await api.guardarPlan(plan);
      setPlan(guardado);
      setAviso("Plan guardado en el vault");
    } catch (err) {
      setAviso(
        err instanceof ErrorApi
          ? `No se pudo guardar el plan: ${err.message}`
          : "No se pudo guardar el plan",
      );
    }
  };

  const lanzarRescueChef = async () => {
    try {
      const sugerencias = await api.rescueChef();
      if (sugerencias.length === 0) {
        setAviso("Rescue Chef: nada que rescatar esta semana");
        return;
      }
      setRescue(sugerencias);
    } catch {
      setAviso("Rescue Chef no disponible");
    }
  };

  const tituloReceta = useCallback(
    (recetaId: string | null | undefined) =>
      recetaId
        ? (recetas ?? []).find((r) => r.id === recetaId)?.titulo ?? recetaId
        : null,
    [recetas],
  );

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <h2 className="mr-auto text-lg font-semibold">
          Semana {plan?.semana_iso ?? semanaISOActual()}
        </h2>
        <button type="button" onClick={lanzarRescueChef} className="boton-secundario">
          Rescue Chef
        </button>
        <button
          type="button"
          onClick={() => setBatchAbierto(true)}
          className="boton-secundario"
        >
          Batch cooking
        </button>
        <button type="button" onClick={guardar} className="boton-primario">
          Guardar
        </button>
      </div>

      {pendiente && <div className="mb-3"><EndpointPendiente ruta={pendiente} /></div>}
      {aviso && (
        <p className="mb-3 rounded-xl border border-emerald-300 bg-emerald-50 p-2.5 text-sm text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-300" role="status">
          {aviso}
        </p>
      )}
      {error && <ErrorWidget mensaje={error} />}
      {(recetas === null || plan === null) && !error && !pendiente && <Cargando />}

      {recetas !== null && plan !== null && (
        <DndContext
          sensors={sensores}
          onDragStart={alEmpezarArrastre}
          onDragEnd={alSoltar}
        >
          {/* Biblioteca de recetas arrastrables */}
          <section aria-label="Recetas disponibles" className="tarjeta-bento mb-4">
            <h3 className="mb-2 text-sm font-semibold">
              Recetas (arrastra a un día)
            </h3>
            {recetas.length === 0 ? (
              <p className="text-sm text-carbon-950/60 dark:text-arena-100/60">
                No hay recetas en el vault.
              </p>
            ) : (
              <ul className="flex gap-2 overflow-x-auto pb-1">
                {recetas.map((receta) => (
                  <RecetaArrastrable key={receta.id} receta={receta} />
                ))}
              </ul>
            )}
          </section>

          {/* Parrilla semanal día x toma */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {DIAS.map((dia) => (
              <section key={dia} className="tarjeta-bento" aria-label={dia}>
                <h3 className="mb-2 text-sm font-semibold capitalize">{dia}</h3>
                <div className="space-y-2">
                  {TOMAS.map((toma) => {
                    const slot: SlotId = `${dia}:${toma}`;
                    const comida = plan.dias[dia]?.[toma];
                    return (
                      <SlotDroppable
                        key={slot}
                        slot={slot}
                        toma={toma}
                        comida={comida}
                        tituloReceta={tituloReceta(comida?.receta_id)}
                        alLimpiar={() => limpiarSlot(slot)}
                      />
                    );
                  })}
                </div>
              </section>
            ))}
          </div>

          {/* Elemento flotante mientras se arrastra */}
          <DragOverlay>
            {recetaArrastrada ? (
              <div className="rounded-xl bg-emerald-600 px-3 py-2 text-sm font-medium text-white shadow-xl">
                {recetaArrastrada.titulo}
              </div>
            ) : null}
          </DragOverlay>
        </DndContext>
      )}

      {rescue && (
        <Modal alCerrar={() => setRescue(null)} titulo="Rescue Chef">
          <ul className="space-y-3">
            {rescue.map((sugerencia) => (
              <li key={sugerencia.receta.id}>
                <p className="font-semibold">
                  {sugerencia.receta.titulo}
                  {sugerencia.stock_critico && (
                    <span className="ml-2 rounded-md bg-red-100 px-1.5 py-0.5 text-xs text-red-700 dark:bg-red-950/60 dark:text-red-300">
                      stock crítico
                    </span>
                  )}
                </p>
                <p className="text-sm">
                  Caduca en {sugerencia.dias_restantes_min} día
                  {sugerencia.dias_restantes_min === 1 ? "" : "s"}
                </p>
                {sugerencia.items_a_rescatar.length > 0 && (
                  <p className="text-sm text-carbon-950/60 dark:text-arena-100/60">
                    Aprovecha:{" "}
                    {sugerencia.items_a_rescatar.map((i) => i.nombre).join(", ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </Modal>
      )}

      {batchAbierto && plan && (
        <ModalBatchCooking
          recetas={recetas ?? []}
          alCerrar={() => setBatchAbierto(false)}
          alProgramar={async (ids, destino) => {
            try {
              const resultado = await api.programarBatchCooking(ids, destino);
              setAviso(
                `Batch cooking completado: ${resultado.tuppers.length} ` +
                  `tupper${resultado.tuppers.length === 1 ? "" : "s"} creado` +
                  `${resultado.tuppers.length === 1 ? "" : "s"} en ${destino}`,
              );
            } catch (err) {
              setAviso(
                err instanceof ErrorApi
                  ? `No se pudo hacer el batch cooking: ${err.message}`
                  : "No se pudo hacer el batch cooking",
              );
            }
            setBatchAbierto(false);
          }}
        />
      )}
    </div>
  );
}

function RecetaArrastrable({ receta }: { receta: Receta }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({ id: receta.id });
  return (
    <li
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      style={
        transform
          ? { transform: `translate(${transform.x}px, ${transform.y}px)` }
          : undefined
      }
      className={`min-h-11 shrink-0 cursor-grab touch-none select-none
        rounded-xl border border-arena-200 bg-arena-50 px-3 py-2 text-sm
        dark:border-carbon-800 dark:bg-carbon-800
        ${isDragging ? "opacity-40" : ""}`}
    >
      <p className="font-medium">{receta.titulo}</p>
      <p className="text-xs opacity-60">
        {receta.tiempo_minutos} min · {receta.raciones} raciones
      </p>
    </li>
  );
}

function SlotDroppable({
  slot,
  toma,
  comida,
  tituloReceta,
  alLimpiar,
}: {
  slot: SlotId;
  toma: (typeof TOMAS)[number];
  comida?: ComidaPlanificada;
  tituloReceta: string | null;
  alLimpiar: () => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: slot });
  const ocupado = Boolean(comida?.receta_id || comida?.plato_libre);

  return (
    <div
      ref={setNodeRef}
      className={`flex min-h-12 items-center justify-between gap-2 rounded-xl
        border border-dashed px-3 py-2 text-sm transition-colors
        ${isOver
          ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/40"
          : "border-arena-200 dark:border-carbon-800"
        }`}
    >
      <span className="text-xs uppercase tracking-wide opacity-50">{toma}</span>
      {ocupado ? (
        <>
          <span className="min-w-0 flex-1 truncate text-right font-medium">
            {tituloReceta ?? comida?.plato_libre}
          </span>
          <button
            type="button"
            onClick={alLimpiar}
            aria-label={`Quitar ${toma}`}
            className="shrink-0 rounded-lg px-2 py-1 text-xs text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40"
          >
            Quitar
          </button>
        </>
      ) : (
        <span className="text-xs opacity-40">Suelta una receta</span>
      )}
    </div>
  );
}

function Modal({
  titulo,
  alCerrar,
  children,
}: {
  titulo: string;
  alCerrar: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={titulo}
      className="fixed inset-0 z-50 flex items-center justify-center bg-carbon-950/50 p-4 backdrop-blur-sm"
      onClick={alCerrar}
    >
      <div
        className="tarjeta-bento w-full max-w-md"
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-base font-semibold">{titulo}</h3>
          <button type="button" onClick={alCerrar} className="boton-secundario">
            Cerrar
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function ModalBatchCooking({
  recetas,
  alCerrar,
  alProgramar,
}: {
  recetas: Receta[];
  alCerrar: () => void;
  alProgramar: (ids: string[], destino: string) => void;
}) {
  const [seleccionadas, setSeleccionadas] = useState<Set<string>>(new Set());
  const [destino, setDestino] = useState("congelador");

  const alternar = (id: string) => {
    setSeleccionadas((prev) => {
      const siguiente = new Set(prev);
      if (siguiente.has(id)) siguiente.delete(id);
      else siguiente.add(id);
      return siguiente;
    });
  };

  return (
    <Modal titulo="Batch cooking" alCerrar={alCerrar}>
      <p className="mb-3 text-sm text-carbon-950/60 dark:text-arena-100/60">
        Descuenta los ingredientes del inventario y crea un tupper por receta.
      </p>
      <fieldset className="mb-3">
        <legend className="mb-1 text-sm">Recetas a preparar</legend>
        <ul className="max-h-48 space-y-1 overflow-y-auto">
          {recetas.map((receta) => (
            <li key={receta.id}>
              <label className="flex min-h-11 items-center gap-2 rounded-xl px-2 text-sm hover:bg-arena-50 dark:hover:bg-carbon-800">
                <input
                  type="checkbox"
                  checked={seleccionadas.has(receta.id)}
                  onChange={() => alternar(receta.id)}
                  className="size-5 accent-emerald-600"
                />
                {receta.titulo}
              </label>
            </li>
          ))}
        </ul>
      </fieldset>
      <label className="mb-4 block text-sm">
        Destino en inventario
        <select
          value={destino}
          onChange={(ev) => setDestino(ev.target.value)}
          className="mt-1 min-h-11 w-full rounded-xl border border-arena-200 bg-arena-50 px-3 dark:border-carbon-800 dark:bg-carbon-800"
        >
          <option value="congelador">Congelador</option>
          <option value="nevera">Nevera</option>
          <option value="despensa">Despensa</option>
        </select>
      </label>
      <button
        type="button"
        disabled={seleccionadas.size === 0}
        onClick={() => alProgramar([...seleccionadas], destino)}
        className="boton-primario w-full"
      >
        Cocinar y crear tuppers
      </button>
    </Modal>
  );
}
