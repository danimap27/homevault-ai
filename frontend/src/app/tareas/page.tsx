"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  addDays,
  addMonths,
  addWeeks,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  startOfMonth,
  startOfWeek,
  subDays,
  subMonths,
  subWeeks,
} from "date-fns";
import { es } from "date-fns/locale";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  PackageX,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import type { CrearTareaInput, Tarea, VistaCalendarioTarea } from "@/lib/types";
import { hoyISO } from "@/lib/utils";
import { Cargando, ErrorWidget } from "@/components/estado-async";
import { FormularioTarea } from "@/components/formulario-tarea";

type Vista = "dia" | "semana" | "mes";

const ESTILO_PRIORIDAD: Record<VistaCalendarioTarea["prioridad"], string> = {
  baja: "bg-slate-700/50 text-slate-300 border-slate-600/30",
  media: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  alta: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  urgente: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

const PUNTO_PRIORIDAD: Record<VistaCalendarioTarea["prioridad"], string> = {
  baja: "bg-slate-400",
  media: "bg-sky-400",
  alta: "bg-amber-400",
  urgente: "bg-rose-400",
};

function aISO(fecha: Date): string {
  return format(fecha, "yyyy-MM-dd");
}

export default function TareasPage() {
  const [vista, setVista] = useState<Vista>("semana");
  const [fecha, setFecha] = useState<Date>(new Date());
  const [tareas, setTareas] = useState<VistaCalendarioTarea[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [modalTarea, setModalTarea] = useState<Tarea | null | "nueva">(null);
  const [diaPanel, setDiaPanel] = useState<Date | null>(null);

  const rango = useMemo(() => {
    const actual = fecha;
    switch (vista) {
      case "dia":
        return { from: aISO(actual), to: aISO(actual) };
      case "semana": {
        const inicio = startOfWeek(actual, { weekStartsOn: 1 });
        const fin = endOfWeek(actual, { weekStartsOn: 1 });
        return { from: aISO(inicio), to: aISO(fin) };
      }
      case "mes": {
        const inicio = startOfMonth(actual);
        const fin = endOfMonth(actual);
        return { from: aISO(inicio), to: aISO(fin) };
      }
    }
  }, [vista, fecha]);

  const cargar = useCallback(async () => {
    try {
      setCargando(true);
      const data = await api.getTareasCalendario(rango.from, rango.to);
      setTareas(data);
      setError(null);
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? `Error ${err.status}: ${err.message}`
          : "API no disponible",
      );
    } finally {
      setCargando(false);
    }
  }, [rango]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const tareasDeDia = (d: Date) =>
    (tareas ?? []).filter((t) => t.fecha === aISO(d));

  const navegarAnterior = () => {
    switch (vista) {
      case "dia":
        setFecha((f) => subDays(f, 1));
        break;
      case "semana":
        setFecha((f) => subWeeks(f, 1));
        break;
      case "mes":
        setFecha((f) => subMonths(f, 1));
        break;
    }
  };

  const navegarSiguiente = () => {
    switch (vista) {
      case "dia":
        setFecha((f) => addDays(f, 1));
        break;
      case "semana":
        setFecha((f) => addWeeks(f, 1));
        break;
      case "mes":
        setFecha((f) => addMonths(f, 1));
        break;
    }
  };

  const irAHoy = () => setFecha(new Date());

  const guardarTarea = async (payload: CrearTareaInput) => {
    try {
      if (modalTarea && modalTarea !== "nueva") {
        await api.actualizarTarea((modalTarea as Tarea).id, payload);
        setAviso("Tarea actualizada");
      } else {
        await api.crearTarea(payload);
        setAviso("Tarea creada");
      }
      setModalTarea(null);
      cargar();
    } catch (err) {
      setAviso(
        err instanceof ErrorApi ? err.message : "No se pudo guardar la tarea",
      );
    }
  };

  const borrarTarea = async (id: string) => {
    if (!confirm("¿Eliminar esta tarea?")) return;
    try {
      await api.borrarTarea(id);
      setAviso("Tarea eliminada");
      cargar();
    } catch (err) {
      setAviso(
        err instanceof ErrorApi ? err.message : "No se pudo eliminar la tarea",
      );
    }
  };

  const completar = async (tarea: VistaCalendarioTarea) => {
    try {
      await api.completarTarea(tarea.task_id);
      setAviso(`Tarea completada: ${tarea.titulo}`);
      cargar();
    } catch (err) {
      setAviso(
        err instanceof ErrorApi ? err.message : "No se pudo completar la tarea",
      );
    }
  };

  const verificarStock = async (tarea: VistaCalendarioTarea) => {
    try {
      const actualizada = await api.verificarStockTarea(tarea.task_id);
      setAviso(
        actualizada.bloqueada_por_stock
          ? `Falta recambio para: ${tarea.titulo}`
          : `Stock OK para: ${tarea.titulo}`,
      );
      cargar();
    } catch (err) {
      setAviso(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo verificar el stock",
      );
    }
  };

  const abrirEditar = async (t: VistaCalendarioTarea) => {
    try {
      const full = await api.getTarea(t.task_id);
      setModalTarea(full);
    } catch (err) {
      setAviso(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo cargar la tarea",
      );
    }
  };

  const tituloFecha = useMemo(() => {
    switch (vista) {
      case "dia":
        return format(fecha, "EEEE, d MMMM", { locale: es });
      case "semana": {
        const inicio = startOfWeek(fecha, { weekStartsOn: 1 });
        const fin = endOfWeek(fecha, { weekStartsOn: 1 });
        return `${format(inicio, "d MMM", { locale: es })} - ${format(fin, "d MMM", { locale: es })}`;
      }
      case "mes":
        return format(fecha, "MMMM yyyy", { locale: es });
    }
  }, [vista, fecha]);

  return (
    <div className="space-y-5">
      {aviso && (
        <p
          className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200"
          role="status"
        >
          {aviso}
        </p>
      )}

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={navegarAnterior}
            className="rounded-xl bg-slate-900/60 p-2 text-slate-300 transition-colors hover:bg-slate-800"
          >
            <ChevronLeft className="size-5" />
          </button>
          <h2 className="min-w-[180px] text-center text-lg font-semibold capitalize">
            {tituloFecha}
          </h2>
          <button
            type="button"
            onClick={navegarSiguiente}
            className="rounded-xl bg-slate-900/60 p-2 text-slate-300 transition-colors hover:bg-slate-800"
          >
            <ChevronRight className="size-5" />
          </button>
        </div>

        <div className="flex items-center justify-between gap-3 sm:justify-start">
          <button
            type="button"
            onClick={irAHoy}
            className="rounded-xl border border-slate-700/50 bg-slate-900/60 px-3 py-2 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-800"
          >
            Hoy
          </button>
          <div className="flex rounded-xl border border-slate-700/50 bg-slate-900/60 p-1">
            {(["dia", "semana", "mes"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setVista(v)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium capitalize transition-all ${
                  vista === v
                    ? "bg-emerald-600 text-white shadow-lg shadow-emerald-900/30"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {v}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && <ErrorWidget mensaje={error} />}
      {!error && (cargando || tareas === null) && <Cargando />}

      {!error && tareas !== null && (
        <>
          {vista === "dia" && (
            <VistaDia
              fecha={fecha}
              tareas={tareasDeDia(fecha)}
              onCompletar={completar}
              onVerificarStock={verificarStock}
              onEditar={abrirEditar}
              onBorrar={borrarTarea}
            />
          )}
          {vista === "semana" && (
            <VistaSemana
              fecha={fecha}
              tareas={tareas ?? []}
              onDia={(d) => {
                setVista("dia");
                setFecha(d);
              }}
              onCompletar={completar}
              onVerificarStock={verificarStock}
              onEditar={abrirEditar}
              onBorrar={borrarTarea}
            />
          )}
          {vista === "mes" && (
            <VistaMes
              fecha={fecha}
              tareas={tareas ?? []}
              onDia={(d) => setDiaPanel(d)}
            />
          )}
        </>
      )}

      <button
        type="button"
        onClick={() => setModalTarea("nueva")}
        className="fixed bottom-24 right-5 z-30 flex size-14 items-center justify-center rounded-full bg-emerald-600 text-white shadow-lg shadow-emerald-900/30 transition-all duration-200 hover:scale-110 hover:bg-emerald-500 active:scale-95"
        aria-label="Nueva tarea"
      >
        <Plus className="size-7" />
      </button>

      {modalTarea && (
        <FormularioTarea
          tarea={modalTarea === "nueva" ? null : modalTarea}
          fechaInicial={vista === "dia" ? aISO(fecha) : undefined}
          onGuardar={guardarTarea}
          onCerrar={() => setModalTarea(null)}
        />
      )}

      {diaPanel && (
        <PanelDia
          fecha={diaPanel}
          tareas={tareasDeDia(diaPanel)}
          onCerrar={() => setDiaPanel(null)}
          onCompletar={completar}
          onVerificarStock={verificarStock}
          onEditar={abrirEditar}
          onBorrar={borrarTarea}
        />
      )}
    </div>
  );
}

function TarjetaTarea({
  tarea,
  onCompletar,
  onVerificarStock,
  onEditar,
  onBorrar,
  compacto = false,
}: {
  tarea: VistaCalendarioTarea;
  onCompletar: (t: VistaCalendarioTarea) => void;
  onVerificarStock: (t: VistaCalendarioTarea) => void;
  onEditar: (t: VistaCalendarioTarea) => void;
  onBorrar: (id: string) => void;
  compacto?: boolean;
}) {
  return (
    <div
      className={`group relative rounded-xl border border-slate-700/30 bg-slate-900/60 p-3 transition-all hover:border-slate-600/50 hover:bg-slate-800/60 ${
        tarea.estado === "completada" ? "opacity-60" : ""
      }`}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <span
          className={`min-w-0 text-sm font-medium leading-tight ${
            tarea.estado === "completada" ? "line-through" : ""
          }`}
        >
          {tarea.titulo}
        </span>
        <span
          className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${ESTILO_PRIORIDAD[tarea.prioridad]}`}
        >
          {tarea.prioridad}
        </span>
      </div>

      {!compacto && (
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-400">
          {tarea.asignado_a && (
            <span className="rounded-full bg-slate-800 px-2 py-0.5">
              {tarea.asignado_a}
            </span>
          )}
          {tarea.bloqueada_por_stock && (
            <span className="inline-flex items-center gap-1 rounded-full bg-rose-950/50 px-2 py-0.5 text-rose-300">
              <PackageX className="size-3" /> Sin stock
            </span>
          )}
        </div>
      )}

      <div className="flex items-center gap-1.5">
        {tarea.estado !== "completada" && (
          <button
            type="button"
            onClick={() => onCompletar(tarea)}
            className="inline-flex flex-1 items-center justify-center gap-1 rounded-lg bg-emerald-600/20 py-1.5 text-xs font-medium text-emerald-300 transition-colors hover:bg-emerald-600/30"
          >
            <Check className="size-3.5" /> Completar
          </button>
        )}
        <button
          type="button"
          onClick={() => onEditar(tarea)}
          className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-slate-100"
          aria-label="Editar"
        >
          <Pencil className="size-4" />
        </button>
        <button
          type="button"
          onClick={() => onBorrar(tarea.task_id)}
          className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-rose-950/50 hover:text-rose-400"
          aria-label="Eliminar"
        >
          <Trash2 className="size-4" />
        </button>
      </div>
    </div>
  );
}

function VistaDia({
  fecha,
  tareas,
  onCompletar,
  onVerificarStock,
  onEditar,
  onBorrar,
}: {
  fecha: Date;
  tareas: VistaCalendarioTarea[];
  onCompletar: (t: VistaCalendarioTarea) => void;
  onVerificarStock: (t: VistaCalendarioTarea) => void;
  onEditar: (t: VistaCalendarioTarea) => void;
  onBorrar: (id: string) => void;
}) {
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium uppercase tracking-wide text-slate-500">
        {format(fecha, "EEEE, d MMMM", { locale: es })}
      </h3>
      {tareas.length === 0 && (
        <p className="py-8 text-center text-sm text-slate-500">
          Sin tareas para este día.
        </p>
      )}
      {tareas.map((t) => (
        <TarjetaTarea
          key={t.task_id}
          tarea={t}
          onCompletar={onCompletar}
          onVerificarStock={onVerificarStock}
          onEditar={onEditar}
          onBorrar={onBorrar}
        />
      ))}
    </div>
  );
}

function VistaSemana({
  fecha,
  tareas,
  onDia,
  onCompletar,
  onVerificarStock,
  onEditar,
  onBorrar,
}: {
  fecha: Date;
  tareas: VistaCalendarioTarea[];
  onDia: (d: Date) => void;
  onCompletar: (t: VistaCalendarioTarea) => void;
  onVerificarStock: (t: VistaCalendarioTarea) => void;
  onEditar: (t: VistaCalendarioTarea) => void;
  onBorrar: (id: string) => void;
}) {
  const dias = useMemo(() => {
    const inicio = startOfWeek(fecha, { weekStartsOn: 1 });
    const fin = endOfWeek(fecha, { weekStartsOn: 1 });
    return eachDayOfInterval({ start: inicio, end: fin });
  }, [fecha]);

  const hoy = new Date();

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-7">
      {dias.map((d) => {
        const deDia = tareas.filter((t) => t.fecha === aISO(d));
        const esHoy = isSameDay(d, hoy);
        return (
          <div
            key={d.toISOString()}
            onClick={() => onDia(d)}
            className={`cursor-pointer rounded-2xl border p-3 transition-all hover:border-slate-600/50 ${
              esHoy
                ? "border-emerald-500/30 bg-emerald-500/5"
                : "border-slate-800 bg-slate-900/30"
            }`}
          >
            <div className="mb-2 text-center">
              <p className="text-xs font-medium uppercase text-slate-500">
                {format(d, "EEE", { locale: es })}
              </p>
              <p
                className={`text-lg font-semibold ${
                  esHoy ? "text-emerald-400" : "text-slate-200"
                }`}
              >
                {format(d, "d")}
              </p>
            </div>
            <div className="space-y-2">
              {deDia.length === 0 && (
                <p className="py-2 text-center text-[10px] text-slate-600">
                  Sin tareas
                </p>
              )}
              {deDia.slice(0, 4).map((t) => (
                <div
                  key={t.task_id}
                  className={`rounded-lg border px-2 py-1.5 text-xs ${ESTILO_PRIORIDAD[t.prioridad]}`}
                >
                  <span className={t.estado === "completada" ? "line-through" : ""}>
                    {t.titulo}
                  </span>
                </div>
              ))}
              {deDia.length > 4 && (
                <p className="text-center text-[10px] text-slate-500">
                  +{deDia.length - 4} más
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function VistaMes({
  fecha,
  tareas,
  onDia,
}: {
  fecha: Date;
  tareas: VistaCalendarioTarea[];
  onDia: (d: Date) => void;
}) {
  const dias = useMemo(() => {
    const inicioMes = startOfMonth(fecha);
    const finMes = endOfMonth(fecha);
    const inicio = startOfWeek(inicioMes, { weekStartsOn: 1 });
    const fin = endOfWeek(finMes, { weekStartsOn: 1 });
    return eachDayOfInterval({ start: inicio, end: fin });
  }, [fecha]);

  const hoy = new Date();

  return (
    <div className="rounded-2xl border border-slate-700/30 bg-slate-900/40 p-3 backdrop-blur">
      <div className="mb-2 grid grid-cols-7 gap-1 text-center text-xs font-medium uppercase text-slate-500">
        {["L", "M", "X", "J", "V", "S", "D"].map((d) => (
          <div key={d}>{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {dias.map((d) => {
          const deDia = tareas.filter((t) => t.fecha === aISO(d));
          const esHoy = isSameDay(d, hoy);
          const delMes = isSameMonth(d, fecha);
          return (
            <button
              key={d.toISOString()}
              type="button"
              onClick={() => onDia(d)}
              className={`aspect-square rounded-xl border p-1 text-left transition-all ${
                esHoy
                  ? "border-emerald-500/40 bg-emerald-500/10"
                  : "border-transparent hover:border-slate-700/50 hover:bg-slate-800/40"
              } ${delMes ? "" : "opacity-40"}`}
            >
              <span
                className={`block text-right text-sm font-medium ${
                  esHoy ? "text-emerald-400" : "text-slate-300"
                }`}
              >
                {format(d, "d")}
              </span>
              <div className="mt-1 flex flex-wrap justify-end gap-1">
                {deDia.slice(0, 4).map((t, i) => (
                  <span
                    key={`${t.task_id}-${i}`}
                    className={`size-1.5 rounded-full ${PUNTO_PRIORIDAD[t.prioridad]}`}
                  />
                ))}
                {deDia.length > 4 && (
                  <span className="text-[8px] text-slate-500">
                    +{deDia.length - 4}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function PanelDia({
  fecha,
  tareas,
  onCerrar,
  onCompletar,
  onVerificarStock,
  onEditar,
  onBorrar,
}: {
  fecha: Date;
  tareas: VistaCalendarioTarea[];
  onCerrar: () => void;
  onCompletar: (t: VistaCalendarioTarea) => void;
  onVerificarStock: (t: VistaCalendarioTarea) => void;
  onEditar: (t: VistaCalendarioTarea) => void;
  onBorrar: (id: string) => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/60 backdrop-blur-sm">
      <div className="flex h-full w-full max-w-sm flex-col border-l border-slate-800 bg-slate-900/95 p-5 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <h3 className="text-lg font-semibold capitalize">
            {format(fecha, "EEEE, d MMMM", { locale: es })}
          </h3>
          <button
            type="button"
            onClick={onCerrar}
            className="rounded-full p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
          >
            <X className="size-5" />
          </button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto">
          {tareas.length === 0 && (
            <p className="py-8 text-center text-sm text-slate-500">
              Sin tareas este día.
            </p>
          )}
          {tareas.map((t) => (
            <TarjetaTarea
              key={t.task_id}
              tarea={t}
              onCompletar={onCompletar}
              onVerificarStock={onVerificarStock}
              onEditar={onEditar}
              onBorrar={onBorrar}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
