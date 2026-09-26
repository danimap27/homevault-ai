/** Utilidades de formato compartidas por las vistas. */

const INVARIABLES = new Set(["dosis", "mes", "paraguas"]);

/**
 * Singulariza unidades en español de forma conservadora:
 * "unidades" → "unidad", "latas" → "lata", "botes" → "bote",
 * "yogures" → "yogur". Si no está claro, devuelve el texto tal cual.
 */
function singularizar(texto: string): string {
  if (texto.length < 4 || !texto.endsWith("s") || INVARIABLES.has(texto)) {
    return texto;
  }
  if (!texto.endsWith("es")) return texto.slice(0, -1);
  // Plural en -es sobre consonante final (unidad→unidades, yogur→yogures)
  const anterior = texto[texto.length - 3];
  if ("dlrnjsxz".includes(anterior)) return texto.slice(0, -2);
  // Plural en -s sobre vocal (bote→botes, lata→latas)
  return texto.slice(0, -1);
}

/**
 * Formatea una cantidad con su unidad con singular/plural coherente:
 * `formatearCantidad(1, "unidades")` → "1 unidad"; `(2, "L")` → "2 L";
 * unidad vacía o ausente → "unidades"/"unidad".
 */
export function formatearCantidad(
  cantidad: number | null | undefined,
  unidad: string | null | undefined,
): string {
  const valor = cantidad ?? 0;
  const texto = (unidad ?? "").trim() || "unidades";
  if (valor === 1) return `1 ${singularizar(texto)}`;
  return `${valor} ${texto}`;
}
