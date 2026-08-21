"use client";

import { useState } from "react";
import { X, Plus, Trash2 } from "lucide-react";
import type {
  ConsumibleRequerido,
  CrearTareaInput,
  Prioridad,
  Tarea,
  Unidad,
} from "@/lib/types";

const FRECUENCIAS = [
  "diaria",
  "semanal",
  "quincenal",
  "mensual",
  "bimestral",
  "trimestral",
  "anual",
  "unica",
];

const PRIORIDADES = ["baja", "media", "alta", "urgente"] as const;

interface FormularioTareaProps {
  tarea: Tarea | null;
  fechaInicial?: string;
  onGuardar: (tarea: CrearTareaInput) => void;
  onCerrar: () => void;
}

export function FormularioTarea({
  tarea,
  fechaInicial,
  onGuardar,
  onCerrar,
}: FormularioTareaProps) {
  const [titulo, setTitulo] = useState(tarea?.titulo ?? "");
  const [zona, setZona] = useState(tarea?.zona ?? "");
  const [frecuencia, setFrecuencia] = useState(tarea?.frecuencia ?? "semanal");
  const [prioridad, setPrioridad] = useState(tarea?.prioridad ?? "media");
  const [asignado, setAsignado] = useState(tarea?.asignado_a ?? "");
  const [rotacion, setRotacion] = useState(
    (tarea?.rotacion_convivientes ?? []).join(", "),
  );
  const [fecha, setFecha] = useState(
    tarea?.fecha_programada ?? fechaInicial ?? "",
  );
  const [estado, setEstado] = useState(tarea?.estado ?? "pendiente");
  const [consumibles, setConsumibles] = useState<ConsumibleRequerido[]>(
    tarea?.consumibles_requeridos?.map((c) => ({
      item_id: c.item_id,
      cantidad: c.cantidad,
      unidad: c.unidad,
      verificar_stock_previo: c.verificar_stock_previo ?? true,
    })) ?? [],
  );

  const agregarConsumible = () => {
    setConsumibles((prev) => [
      ...prev,
      { item_id: "", cantidad: 1, unidad: "unidades", verificar_stock_previo: true },
    ]);
  };

  const actualizarConsumible = (
    idx: number,
    campo: keyof ConsumibleRequerido,
    valor: string | number | boolean,
  ) => {
    setConsumibles((prev) =>
      prev.map((c, i) =>
        i === idx
          ? {
              ...c,
              [campo]:
                campo === "cantidad"
                  ? Number(valor)
                  : campo === "verificar_stock_previo"
                    ? Boolean(valor)
                    : valor,
            }
          : c,
      ),
    );
  };

  const borrarConsumible = (idx: number) => {
    setConsumibles((prev) => prev.filter((_, i) => i !== idx));
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: CrearTareaInput = {
      titulo: titulo.trim(),
      zona: zona.trim() || null,
      frecuencia,
      prioridad,
      asignado_a: asignado.trim() || null,
      rotacion_convivientes: rotacion
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      fecha_programada: fecha || null,
      estado,
      consumibles_requeridos: consumibles.filter((c) => c.item_id.trim() !== ""),
    };
    onGuardar(payload);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 py-6 backdrop-blur-sm">
      <div className="flex max-h-full w-full max-w-lg flex-col overflow-hidden rounded-3xl border border-slate-700/50 bg-slate-900/95 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <h3 className="text-lg font-semibold">
            {tarea ? "Editar tarea" : "Nueva tarea"}
          </h3>
          <button
            type="button"
            onClick={onCerrar}
            className="rounded-full p-1 text-slate-400 transition-colors hover:bg-slate-800 hover:text-white"
          >
            <X className="size-5" />
          </button>
        </div>

        <form
          onSubmit={submit}
          className="flex-1 overflow-y-auto px-6 py-5"
        >
          <div className="space-y-5">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-300">
                Título *
              </label>
              <input
                type="text"
                required
                value={titulo}
                onChange={(e) => setTitulo(e.target.value)}
                placeholder="Ej. Limpiar filtros"
                className="input-premium"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">
                  Zona
                </label>
                <input
                  type="text"
                  value={zona}
                  onChange={(e) => setZona(e.target.value)}
                  placeholder="Ej. Cocina"
                  className="input-premium"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">
                  Frecuencia
                </label>
                <select
                  value={frecuencia}
                  onChange={(e) => setFrecuencia(e.target.value)}
                  className="input-premium"
                >
                  {FRECUENCIAS.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">
                  Prioridad
                </label>
                <select
                  value={prioridad}
                  onChange={(e) => setPrioridad(e.target.value as Prioridad)}
                  className="input-premium"
                >
                  {PRIORIDADES.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">
                  Asignado a
                </label>
                <input
                  type="text"
                  value={asignado}
                  onChange={(e) => setAsignado(e.target.value)}
                  placeholder="Ej. Dani"
                  className="input-premium"
                />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-300">
                Rotación de convivientes
              </label>
              <input
                type="text"
                value={rotacion}
                onChange={(e) => setRotacion(e.target.value)}
                placeholder="Separados por comas: Dani, Marta, Leo"
                className="input-premium"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">
                  Fecha programada
                </label>
                <input
                  type="date"
                  value={fecha}
                  onChange={(e) => setFecha(e.target.value)}
                  className="input-premium"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">
                  Estado
                </label>
                <select
                  value={estado}
                  onChange={(e) => setEstado(e.target.value as Tarea["estado"])}
                  className="input-premium"
                >
                  <option value="pendiente">Pendiente</option>
                  <option value="completada">Completada</option>
                </select>
              </div>
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <label className="text-sm font-medium text-slate-300">
                  Consumibles requeridos
                </label>
                <button
                  type="button"
                  onClick={agregarConsumible}
                  className="inline-flex items-center gap-1 rounded-lg bg-slate-800 px-2 py-1 text-xs font-medium text-slate-300 transition-colors hover:bg-slate-700"
                >
                  <Plus className="size-3.5" /> Añadir
                </button>
              </div>
              <div className="space-y-2">
                {consumibles.map((c, idx) => (
                  <div
                    key={idx}
                    className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/40 p-2"
                  >
                    <input
                      type="text"
                      value={c.item_id}
                      onChange={(e) =>
                        actualizarConsumible(idx, "item_id", e.target.value)
                      }
                      placeholder="item_id"
                      className="input-premium min-w-0 flex-1 px-2 py-1.5 text-xs"
                    />
                    <input
                      type="number"
                      min={0}
                      step="0.01"
                      value={c.cantidad}
                      onChange={(e) =>
                        actualizarConsumible(idx, "cantidad", e.target.value)
                      }
                      className="input-premium w-20 px-2 py-1.5 text-xs"
                    />
                    <select
                      value={c.unidad}
                      onChange={(e) =>
                        actualizarConsumible(idx, "unidad", e.target.value as Unidad)
                      }
                      className="input-premium w-28 px-2 py-1.5 text-xs"
                    >
                      <option value="unidades">unidades</option>
                      <option value="litros">litros</option>
                      <option value="kg">kg</option>
                      <option value="gramos">gramos</option>
                      <option value="pastillas">pastillas</option>
                      <option value="dosis">dosis</option>
                    </select>
                    <button
                      type="button"
                      onClick={() => borrarConsumible(idx)}
                      className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-950/50 hover:text-rose-400"
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </form>

        <div className="flex gap-3 border-t border-slate-800 px-6 py-4">
          <button
            type="button"
            onClick={onCerrar}
            className="boton-secundario flex-1"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={!titulo.trim()}
            onClick={submit}
            className="boton-primario flex-1"
          >
            {tarea ? "Guardar cambios" : "Crear tarea"}
          </button>
        </div>
      </div>
    </div>
  );
}
