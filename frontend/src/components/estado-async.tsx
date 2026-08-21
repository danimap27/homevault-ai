/**
 * Estados compartidos de carga/error para los widgets que consumen la API.
 */

export function Cargando({ texto = "Cargando…" }: { texto?: string }) {
  return (
    <p className="animate-pulse text-sm text-carbon-950/50 dark:text-arena-100/50">
      {texto}
    </p>
  );
}

export function ErrorWidget({ mensaje }: { mensaje: string }) {
  return (
    <p className="text-sm text-red-600 dark:text-red-400" role="alert">
      {mensaje}
    </p>
  );
}

/** Mensaje amable cuando un endpoint del spec aún no existe en el backend. */
export function EndpointPendiente({ ruta }: { ruta: string }) {
  return (
    <p className="text-sm text-amber-600 dark:text-amber-400">
      Endpoint pendiente en el backend: <code>{ruta}</code>
    </p>
  );
}
