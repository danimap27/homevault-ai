/**
 * Cliente de la API FastAPI de HomeVault AI.
 *
 * La base URL se configura con la variable de entorno NEXT_PUBLIC_API_URL
 * (ver frontend/.env.local.example). Todas las rutas llamadas aquí existen
 * en backend/main.py o en los routers de backend/routers/.
 */

import type {
  Consumible,
  EntradaListaCompra,
  ItemCaducidad,
  PlanSemanal,
  Receta,
  RespuestaCheckLista,
  ResultadoBatchCooking,
  ResultadoCompra,
  ResultadoConsumo,
  ResultadoImpresion,
  ResumenFinanciero,
  SugerenciaRescate,
  Tarea,
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Error de la API con el status HTTP y el detalle devuelto por FastAPI. */
export class ErrorApi extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ErrorApi";
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: init?.body
      ? { "Content-Type": "application/json", ...init?.headers }
      : init?.headers,
  });
  if (!resp.ok) {
    let detalle = resp.statusText;
    try {
      const cuerpo = await resp.json();
      detalle = cuerpo.detail ?? detalle;
    } catch {
      // Respuesta sin cuerpo JSON: se conserva el statusText.
    }
    throw new ErrorApi(resp.status, String(detalle));
  }
  return (await resp.json()) as T;
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: "POST",
    body: body === undefined ? null : JSON.stringify(body),
  });
}

export const api = {
  // --- Inventario (endpoints reales de backend/main.py) --------------------

  getInventario: (ubicacion?: string) =>
    apiFetch<Consumible[]>(
      `/api/inventory${ubicacion ? `?ubicacion=${encodeURIComponent(ubicacion)}` : ""}`,
    ),

  getCaducidades: (daysAhead = 5) =>
    apiFetch<ItemCaducidad[]>(`/api/inventory/expiring?days_ahead=${daysAhead}`),

  consumirItem: (itemIdONombre: string, cantidad: number) =>
    post<ResultadoConsumo>("/api/inventory/consume", {
      item_id_o_nombre: itemIdONombre,
      cantidad,
    }),

  registrarCompra: (
    itemIdONombre: string,
    cantidad: number,
    precioUnitario: number,
    fechaCaducidad?: string,
  ) =>
    post<ResultadoCompra>("/api/inventory/purchase", {
      item_id_o_nombre: itemIdONombre,
      cantidad,
      precio_unitario: precioUnitario,
      ...(fechaCaducidad ? { fecha_caducidad: fechaCaducidad } : {}),
    }),

  // --- Tareas (endpoints reales) --------------------------------------------

  getTareasPendientes: (assignedUser?: string) =>
    apiFetch<Tarea[]>(
      `/api/tasks/pending${assignedUser ? `?assigned_user=${encodeURIComponent(assignedUser)}` : ""}`,
    ),

  completarTarea: (taskId: string, completedBy?: string) =>
    post<Tarea>(`/api/tasks/${encodeURIComponent(taskId)}/complete`, {
      completed_by: completedBy ?? null,
    }),

  verificarStockTarea: (taskId: string) =>
    post<Tarea>(`/api/tasks/${encodeURIComponent(taskId)}/check-stock`),

  /** GET /api/tasks?estado=completada */
  getTareasCompletadas: () =>
    apiFetch<Tarea[]>("/api/tasks?estado=completada"),

  // --- Lista de la compra -----------------------------------------------------

  getListaCompra: () => apiFetch<EntradaListaCompra[]>("/api/shopping-list"),

  /** POST /api/shopping-list/check {item_id} */
  checkEntradaLista: (itemId: string) =>
    post<RespuestaCheckLista>("/api/shopping-list/check", { item_id: itemId }),

  /** POST /api/print/receipt-list (impresora térmica) */
  imprimirListaCompra: () => post<ResultadoImpresion>("/api/print/receipt-list"),

  // --- Recetas y planificador ---------------------------------------------------

  /** GET /api/recipes */
  getRecetas: () => apiFetch<Receta[]>("/api/recipes"),

  /** GET /api/planner/current (semana ISO actual) */
  getPlanActual: () => apiFetch<PlanSemanal>("/api/planner/current"),

  /** PUT /api/planner/current */
  guardarPlan: (plan: PlanSemanal) =>
    apiFetch<PlanSemanal>("/api/planner/current", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(plan),
    }),

  /** GET /api/planner/rescue?dias= (Rescue Chef) */
  rescueChef: (dias = 4) =>
    apiFetch<SugerenciaRescate[]>(`/api/planner/rescue?dias=${dias}`),

  /** POST /api/planner/batch-cooking (descuenta crudos y crea tuppers) */
  programarBatchCooking: (
    recetaIds: string[],
    destino: string,
    diasMaxCongelador?: number,
  ) =>
    post<ResultadoBatchCooking>("/api/planner/batch-cooking", {
      receta_ids: recetaIds,
      destino,
      ...(diasMaxCongelador ? { dias_max_congelador: diasMaxCongelador } : {}),
    }),

  // --- Finanzas ------------------------------------------------------------------

  /** GET /api/finance/summary?mes=YYYY-MM */
  getResumenFinanciero: (mes: string) =>
    apiFetch<ResumenFinanciero>(
      `/api/finance/summary?mes=${encodeURIComponent(mes)}`,
    ),

  // --- Ingesta de tickets (endpoint real) ----------------------------------------

  ingerirTicketTexto: (texto: string, comercio?: string, total?: number) =>
    post<unknown>("/api/ingest/receipt", { texto, comercio, total }),

  /** Sube la foto del ticket como multipart/form-data (campo "imagen"). */
  ingerirTicketImagen: async (archivo: File): Promise<unknown> => {
    const form = new FormData();
    form.append("imagen", archivo);
    const resp = await fetch(`${API_URL}/api/ingest/receipt`, {
      method: "POST",
      body: form, // sin Content-Type: el navegador pone el boundary
    });
    if (!resp.ok) {
      let detalle = resp.statusText;
      try {
        detalle = (await resp.json()).detail ?? detalle;
      } catch {
        // Sin cuerpo JSON.
      }
      throw new ErrorApi(resp.status, String(detalle));
    }
    return resp.json();
  },
};
