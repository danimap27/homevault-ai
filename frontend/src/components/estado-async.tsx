"use client";

import { Loader2 } from "lucide-react";

export function Cargando({ texto = "Cargando…" }: { texto?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500">
      <Loader2 className="size-4 animate-spin" />
      {texto}
    </div>
  );
}

export function ErrorWidget({ mensaje }: { mensaje: string }) {
  return (
    <p className="rounded-xl border border-rose-500/20 bg-rose-500/10 p-3 text-sm text-rose-200" role="alert">
      {mensaje}
    </p>
  );
}

export function EndpointPendiente({ ruta }: { ruta: string }) {
  return (
    <p className="text-sm text-amber-400">
      Endpoint pendiente en el backend: <code>{ruta}</code>
    </p>
  );
}
