/**
 * Cliente de la API FastAPI de HomeVault AI.
 *
 * La base URL se configura con la variable de entorno NEXT_PUBLIC_API_URL
 * (ver frontend/.env.local.example). Todas las rutas llamadas aquí existen
 * en backend/main.py o en los routers de backend/routers/.
 */

import type {
  ActualizarTareaInput,
  Consumible,
  CrearPerfilInput,
  CrearTareaInput,
  EntradaListaCompra,
  ItemCaducidad,
  Perfil,
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
  VistaCalendarioTarea,
} from "./types";

// --- Tipos para endpoints de escaneo de códigos de barras --------------------

export interface RespuestaBarcode {
  item: Consumible;
  creado: boolean;
  origen: string;
}

export interface RespuestaConsumoBarcode {
  resultado: ResultadoConsumo;
  quitado_de_lista: number;
}

export interface SugerenciaFusion {
  id: string;
  nombre: string;
  ean_barcode: string | null;
}

export interface RespuestaBarcodeNoEncontrado {
  detail: string;
  ean: string;
  sugerencias: SugerenciaFusion[];
}

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

function put<T>(path: string, body?: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: "PUT",
    body: body === undefined ? null : JSON.stringify(body),
  });
}

function del<T>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: "DELETE" });
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

  /** GET /api/tasks/{id} */
  getTarea: (id: string) => apiFetch<Tarea>(`/api/tasks/${encodeURIComponent(id)}`),

  /** POST /api/tasks */
  crearTarea: (tarea: CrearTareaInput) => post<Tarea>("/api/tasks", tarea),

  /** PUT /api/tasks/{id} */
  actualizarTarea: (id: string, tarea: ActualizarTareaInput) =>
    put<Tarea>(`/api/tasks/${encodeURIComponent(id)}`, tarea),

  /** DELETE /api/tasks/{id} */
  borrarTarea: (id: string) => del<void>(`/api/tasks/${encodeURIComponent(id)}`),

  /** GET /api/tasks/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD */
  getTareasCalendario: (from: string, to: string) =>
    apiFetch<VistaCalendarioTarea[]>(
      `/api/tasks/calendar?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
    ),

  // --- Perfiles ---------------------------------------------------------------

  getPerfiles: () => apiFetch<Perfil[]>("/api/profiles"),

  crearPerfil: (perfil: CrearPerfilInput) => post<Perfil>("/api/profiles", perfil),

  actualizarPerfil: (id: string, perfil: CrearPerfilInput) =>
    put<Perfil>(`/api/profiles/${encodeURIComponent(id)}`, perfil),

  borrarPerfil: (id: string) => del<void>(`/api/profiles/${encodeURIComponent(id)}`),

  verificarPinPerfil: (id: string, pin: string) =>
    post<{ valido: boolean }>(`/api/profiles/${encodeURIComponent(id)}/verify-pin`, { pin }),

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

  // --- Escaneo de códigos de barras -------------------------------------------

  /** GET /api/barcode/{ean}: devuelve el ítem o un 404 con sugerencias. */
  escanearBarcode: async (
    ean: string,
  ): Promise<RespuestaBarcode | RespuestaBarcodeNoEncontrado> => {
    const resp = await fetch(`${API_URL}/api/barcode/${encodeURIComponent(ean)}`);
    if (resp.status === 404) {
      return (await resp.json()) as RespuestaBarcodeNoEncontrado;
    }
    if (!resp.ok) {
      let detalle = resp.statusText;
      try {
        detalle = (await resp.json()).detail ?? detalle;
      } catch {
        // Sin cuerpo JSON.
      }
      throw new ErrorApi(resp.status, String(detalle));
    }
    return (await resp.json()) as RespuestaBarcode;
  },

  /** POST /api/barcode/consume {ean, cantidad}. */
  consumirPorBarcode: (ean: string, cantidad = 1) =>
    post<RespuestaConsumoBarcode>("/api/barcode/consume", { ean, cantidad }),

  /** POST /api/barcode/register multipart/form-data. */
  registrarBarcode: async (formData: FormData): Promise<Consumible> => {
    const resp = await fetch(`${API_URL}/api/barcode/register`, {
      method: "POST",
      body: formData, // sin Content-Type: el navegador pone el boundary
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
    return (await resp.json()) as Consumible;
  },
};
