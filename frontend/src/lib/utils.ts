/**
 * Utilidades de fechas y formato para la PWA.
 */

/** Devuelve la fecha local en formato ISO "YYYY-MM-DD". */
export function hoyISO(): string {
  const ahora = new Date();
  return aFechaISO(ahora);
}

function aFechaISO(fecha: Date): string {
  const y = fecha.getFullYear();
  const m = String(fecha.getMonth() + 1).padStart(2, "0");
  const d = String(fecha.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** Semana ISO 8601 actual en formato "YYYY-Www" (ej. "2026-W34"). */
export function semanaISOActual(): string {
  const ahora = new Date();
  // Jueves de la semana actual: define el año ISO según ISO 8601.
  const jueves = new Date(ahora);
  jueves.setDate(ahora.getDate() + 3 - ((ahora.getDay() + 6) % 7));
  const primerJueves = new Date(jueves.getFullYear(), 0, 4);
  const semana =
    1 +
    Math.round(
      ((jueves.getTime() - primerJueves.getTime()) / 86400000 -
        3 +
        ((primerJueves.getDay() + 6) % 7)) /
        7,
    );
  return `${jueves.getFullYear()}-W${String(semana).padStart(2, "0")}`;
}

/** Mes actual en formato "YYYY-MM" para el widget financiero. */
export function mesActual(): string {
  const ahora = new Date();
  return `${ahora.getFullYear()}-${String(ahora.getMonth() + 1).padStart(2, "0")}`;
}

/** Formatea un importe en euros con el locale español. */
export function formatoEuros(importe: number): string {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
  }).format(importe);
}

/** Etiqueta corta de fecha en español (ej. "jue 21 ago"). */
export function formatoFechaCorta(fechaISO: string): string {
  const fecha = new Date(`${fechaISO}T00:00:00`);
  return new Intl.DateTimeFormat("es-ES", {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(fecha);
}
