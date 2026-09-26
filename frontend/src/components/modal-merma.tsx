"use client";

import { useState } from "react";
import { Loader2, PackageX, X } from "lucide-react";
import { api, ErrorApi } from "@/lib/api";
import type { Consumible, MotivoMerma } from "@/lib/types";

const MOTIVOS: { id: MotivoMerma; etiqueta: string }[] = [
  { id: "caducado", etiqueta: "Caducado" },
  { id: "estropeado", etiqueta: "Estropeado" },
  { id: "no_deseado", etiqueta: "Ya no lo queremos" },
  { id: "otro", etiqueta: "Otro" },
];

/**
 * Modal para registrar una merma (producto tirado): descuenta del stock y
 * la anota en el histórico de desperdicio del mes.
 */
export function ModalMerma({
  item,
  onCerrar,
  onExito,
}: {
  item: Consumible;
  onCerrar: () => void;
  onExito: (mensaje: string) => void;
}) {
  const [cantidad, setCantidad] = useState(1);
  const [motivo, setMotivo] = useState<MotivoMerma>("caducado");
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enviar = async () => {
    setCargando(true);
    setError(null);
    try {
      const resultado = await api.registrarMerma(item.id, cantidad, motivo);
      const valor =
        resultado.valor_estimado > 0
          ? ` (~${resultado.valor_estimado.toFixed(2)} €)`
          : "";
      onExito(
        `Merma registrada: ${resultado.cantidad} ${item.unidad} de ${resultado.nombre}${valor}. ` +
          `Llevas ${resultado.resumen_mes.total_registros} este mes.`,
      );
    } catch (err) {
      setError(
        err instanceof ErrorApi
          ? err.message
          : "No se pudo registrar la merma",
      );
    } finally {
      setCargando(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Registrar merma de ${item.nombre}`}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
      onClick={onCerrar}
    >
      <div
        className="w-full max-w-md rounded-3xl border border-slate-700/30 bg-slate-900/90 p-6 shadow-2xl"
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-100">
            <PackageX className="size-5 text-amber-400" />
            Registrar merma
          </h3>
          <button type="button" onClick={onCerrar} className="boton-secundario">
            <X className="size-4" />
          </button>
        </div>
        <p className="mb-4 text-sm text-slate-400">
          Producto tirado de <strong>{item.nombre}</strong>. Stock actual:{" "}
          {item.stock_actual} {item.unidad}.
        </p>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Cantidad ({item.unidad})
              </label>
              <input
                type="number"
                min="0.01"
                max={item.stock_actual}
                step={item.unidad === "unidades" ? 1 : 0.01}
                value={cantidad}
                onChange={(ev) => setCantidad(Number(ev.target.value))}
                className="input-premium"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-300">
                Motivo
              </label>
              <select
                value={motivo}
                onChange={(ev) => setMotivo(ev.target.value as MotivoMerma)}
                className="input-premium"
              >
                {MOTIVOS.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.etiqueta}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {error && (
            <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-2 text-sm text-rose-200">
              {error}
            </p>
          )}

          <button
            type="button"
            onClick={enviar}
            disabled={cargando || cantidad <= 0}
            className="boton-primario w-full justify-center bg-amber-600 hover:bg-amber-500"
          >
            {cargando ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <>
                <PackageX className="size-4" /> Registrar merma
              </>
            )}
          </button>
          <p className="text-center text-xs text-slate-500">
            Se descuenta del stock y se anota en el desperdicio del mes.
          </p>
        </div>
      </div>
    </div>
  );
}
