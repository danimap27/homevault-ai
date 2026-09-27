/**
 * Cliente de la API FastAPI de HomeVault AI.
 *
 * La base URL se configura con la variable de entorno NEXT_PUBLIC_API_URL
 * (ver frontend/.env.local.example). Todas las rutas llamadas aquí existen
 * en backend/main.py o en los routers de backend/routers/.
 */

import type {
  ActualizarConsumibleInput,
  ActualizarRecetaInput,
  ActualizarTareaInput,
  AsignarPlanInput,
  Categoria,
  CocinarRecetaInput,
  CocinarRecetaResultado,
  Consumible,
  CrearConsumibleInput,
  CrearPerfilInput,
  CrearRecetaInput,
  CrearTareaInput,
  EntradaListaCompra,
  EstadisticasTareas,
  ItemCaducidad,
  LocalBarcode,
  MotivoMerma,
  MoverItemInput,
  Perfil,
  PlanSemanal,
  PrediccionAgotamiento,
  Receta,
  RecetaPosible,
  RespuestaBorrarLista,
  RespuestaCheckLista,
  RespuestaChat,
  RespuestaEditarLista,
  ResumenDesperdicio,
  ResumenFinanciero,
  ResumenInteligencia,
  ResultadoBatchCooking,
  ResultadoCompra,
  ResultadoConsumo,
  ResultadoDesperdicio,
  ResultadoImpresion,
  SugerenciaReposicion,
  SugerenciaRescate,
  Supermercado,
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

/** Error de la API con el status HTTP, el detalle devuelto por FastAPI y el
 *  cuerpo JSON completo cuando está disponible. */
export class ErrorApi extends Error {
  constructor(
    public status: number,
    message: string,
    public data?: unknown,
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
    let cuerpo: unknown = undefined;
    try {
      cuerpo = await resp.json();
      detalle = String((cuerpo as { detail?: unknown }).detail ?? detalle);
    } catch {
      // Respuesta sin cuerpo JSON: se conserva el statusText.
    }
    throw new ErrorApi(resp.status, String(detalle), cuerpo);
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

function delQuery<T>(path: string): Promise<T> {
  return apiFetch<T>(path, { method: "DELETE" });
}

export const api = {
  // --- Inventario (endpoints reales de backend/main.py) --------------------

  getInventario: (ubicacion?: string) =>
    apiFetch<Consumible[]>(
      `/api/inventory${ubicacion ? `?ubicacion=${encodeURIComponent(ubicacion)}` : ""}`,
    ),

  crearItem: (item: CrearConsumibleInput) =>
    post<Consumible>("/api/inventory", item),

  actualizarItem: (id: string, item: ActualizarConsumibleInput) =>
    put<Consumible>(`/api/inventory/${encodeURIComponent(id)}`, item),

  borrarItem: (id: string) => del<void>(`/api/inventory/${encodeURIComponent(id)}`),

  moverItem: (id: string, cambios: MoverItemInput) =>
    post<Consumible>(`/api/inventory/${encodeURIComponent(id)}/move`, cambios),

  getCaducidades: (daysAhead = 5) =>
    apiFetch<ItemCaducidad[]>(`/api/inventory/expiring?days_ahead=${daysAhead}`),

  // --- Categorías dinámicas ----------------------------------------------------

  getCategorias: () => apiFetch<Categoria[]>("/api/categories"),

  crearCategoria: (categoria: Categoria) =>
    post<Categoria>("/api/categories", categoria),

  actualizarCategoria: (id: string, cambios: Partial<Categoria>) =>
    put<Categoria>(`/api/categories/${encodeURIComponent(id)}`, cambios),

  /** DELETE /api/categories/{id}?reemplazar_por=otra_id. El 409 con ítems se
   *  maneja en el componente para pedir la categoría de reemplazo. */
  borrarCategoria: (id: string, reemplazarPor?: string) =>
    delQuery<void>(
      `/api/categories/${encodeURIComponent(id)}${reemplazarPor ? `?reemplazar_por=${encodeURIComponent(reemplazarPor)}` : ""}`,
    ),

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
    supermercado?: string,
  ) =>
    post<ResultadoCompra>("/api/inventory/purchase", {
      item_id_o_nombre: itemIdONombre,
      cantidad,
      precio_unitario: precioUnitario,
      ...(fechaCaducidad ? { fecha_caducidad: fechaCaducidad } : {}),
      ...(supermercado ? { supermercado } : {}),
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

  /** DELETE /api/shopping-list/{item_id} */
  borrarEntradaLista: (itemId: string) =>
    del<RespuestaBorrarLista>(`/api/shopping-list/${encodeURIComponent(itemId)}`),

  /** PUT /api/shopping-list/{item_id} {cantidad?, unidad?, categoria?} */
  editarEntradaLista: (
    itemId: string,
    cambios: { cantidad?: number; unidad?: string; categoria?: string },
  ) =>
    put<RespuestaEditarLista>(
      `/api/shopping-list/${encodeURIComponent(itemId)}`,
      cambios,
    ),

  /** POST /api/print/receipt-list (impresora térmica) */
  imprimirListaCompra: () => post<ResultadoImpresion>("/api/print/receipt-list"),

  // --- Recetas y planificador ---------------------------------------------------

  /** GET /api/recipes */
  getRecetas: () => apiFetch<Receta[]>("/api/recipes"),

  /** GET /api/recipes/{id} */
  getReceta: (id: string) => apiFetch<Receta>(`/api/recipes/${encodeURIComponent(id)}`),

  /** POST /api/recipes */
  crearReceta: (receta: CrearRecetaInput) => post<Receta>("/api/recipes", receta),

  /** PUT /api/recipes/{id} */
  actualizarReceta: (id: string, receta: ActualizarRecetaInput) =>
    put<Receta>(`/api/recipes/${encodeURIComponent(id)}`, receta),

  /** DELETE /api/recipes/{id} */
  borrarReceta: (id: string) => del<void>(`/api/recipes/${encodeURIComponent(id)}`),

  /** GET /api/recipes/possible */
  getRecetasPosibles: () => apiFetch<RecetaPosible[]>("/api/recipes/possible"),

  /** POST /api/recipes/{id}/cook */
  cocinarReceta: (id: string, input?: CocinarRecetaInput) =>
    post<CocinarRecetaResultado>(`/api/recipes/${encodeURIComponent(id)}/cook`, input ?? {}),

  /** GET /api/planner/current (semana ISO actual) */
  getPlanActual: () => apiFetch<PlanSemanal>("/api/planner/current"),

  /** POST /api/planner/assign */
  asignarPlan: (input: AsignarPlanInput) =>
    post<CocinarRecetaResultado>("/api/planner/assign", input),

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

  ingerirTicketTexto: (
    texto: string,
    comercio?: string,
    total?: number,
    supermercado?: string,
  ) =>
    post<unknown>("/api/ingest/receipt", {
      texto,
      comercio,
      total,
      ...(supermercado ? { supermercado } : {}),
    }),

  /** Sube la foto del ticket como multipart/form-data (campo "imagen"). */
  ingerirTicketImagen: async (
    archivo: File,
    supermercado?: string,
  ): Promise<unknown> => {
    const form = new FormData();
    form.append("imagen", archivo);
    if (supermercado) form.append("supermercado", supermercado);
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

  // --- Supermercados ----------------------------------------------------------

  getSupermercados: () => apiFetch<Supermercado[]>("/api/supermarkets"),

  crearSupermercado: (nombre: string) =>
    post<Supermercado>("/api/supermarkets", { nombre }),

  actualizarSupermercado: (
    id: string,
    cambios: { nombre?: string; predeterminado?: boolean },
  ) => put<Supermercado>(`/api/supermarkets/${encodeURIComponent(id)}`, cambios),

  borrarSupermercado: (id: string) =>
    del<void>(`/api/supermarkets/${encodeURIComponent(id)}`),

  // --- Base de datos local de códigos de barras -------------------------------

  getLocalBarcodes: () => apiFetch<LocalBarcode[]>("/api/local-barcodes"),

  getLocalBarcode: (ean: string) =>
    apiFetch<LocalBarcode>(`/api/local-barcodes/${encodeURIComponent(ean)}`),

  crearLocalBarcode: (barcode: LocalBarcode) =>
    post<LocalBarcode>("/api/local-barcodes", barcode),

  actualizarLocalBarcode: (ean: string, barcode: LocalBarcode) =>
    put<LocalBarcode>(`/api/local-barcodes/${encodeURIComponent(ean)}`, barcode),

  borrarLocalBarcode: (ean: string) =>
    del<void>(`/api/local-barcodes/${encodeURIComponent(ean)}`),

  // --- Inteligencia del hogar (Fase 7) -----------------------------------------

  /** GET /api/insights: panel completo de inteligencia del hogar. */
  getInsights: () => apiFetch<ResumenInteligencia>("/api/insights"),

  /** GET /api/insights/predictions: agotamiento estimado por ítem. */
  getPredicciones: () =>
    apiFetch<PrediccionAgotamiento[]>("/api/insights/predictions"),

  /** GET /api/insights/restock: sugerencias de reposición priorizadas. */
  getReposicion: () =>
    apiFetch<SugerenciaReposicion[]>("/api/insights/restock"),

  /** GET /api/insights/waste: desperdicio de un mes (por defecto, actual). */
  getDesperdicio: (mes?: string) =>
    apiFetch<ResumenDesperdicio>(
      `/api/insights/waste${mes ? `?mes=${encodeURIComponent(mes)}` : ""}`,
    ),

  /** GET /api/insights/tasks: estadísticas de tareas y equidad. */
  getEstadisticasTareas: (mes?: string) =>
    apiFetch<EstadisticasTareas>(
      `/api/insights/tasks${mes ? `?mes=${encodeURIComponent(mes)}` : ""}`,
    ),

  /** POST /api/inventory/{item_id}/waste: registra una merma. */
  registrarMerma: (itemId: string, cantidad: number, motivo: MotivoMerma) =>
    post<ResultadoDesperdicio>(
      `/api/inventory/${encodeURIComponent(itemId)}/waste`,
      { cantidad, motivo },
    ),

  /** POST /api/tasks/{task_id}/snooze: pospone N días. */
  posponerTarea: (taskId: string, dias: number) =>
    post<Tarea>(`/api/tasks/${encodeURIComponent(taskId)}/snooze`, { dias }),

  /** POST /api/ai/chat: pregunta al asistente del hogar. */
  chatear: (mensaje: string) =>
    post<RespuestaChat>("/api/ai/chat", { mensaje }),

  /**
   * Asistente con respuesta incremental: crea un job de generación y consulta
   * su estado cada segundo hasta terminar. Se evita SSE porque Cloudflare
   * bufferiza los streams a través del túnel del homelab.
   * Invoca `onMeta` al conocer el contexto y `onToken` por cada delta de texto.
   */
  chatearStream: async (
    mensaje: string,
    callbacks: {
      onMeta?: (meta: { items: number; tareas: number }) => void;
      onToken: (texto: string) => void;
    },
  ): Promise<void> => {
    interface EstadoJobChat {
      job_id: string;
      estado: "generando" | "fin" | "error";
      texto: string;
      meta: { items?: number; tareas?: number };
      detalle: string | null;
    }
    const crear = await fetch(`${API_URL}/api/ai/chat/job`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje }),
    });
    if (!crear.ok) {
      let detalle = crear.statusText;
      try {
        const cuerpo = (await crear.json()) as { detail?: unknown };
        detalle = String(cuerpo.detail ?? detalle);
      } catch {
        // respuesta sin cuerpo JSON
      }
      throw new ErrorApi(crear.status, detalle);
    }
    const { job_id } = (await crear.json()) as EstadoJobChat;

    let visto = 0;
    let metaEnviada = false;
    for (;;) {
      await new Promise((r) => setTimeout(r, 1000));
      const estado = await apiFetch<EstadoJobChat>(
        `/api/ai/chat/job/${encodeURIComponent(job_id)}`,
      );
      if (
        !metaEnviada &&
        estado.meta &&
        typeof estado.meta.items === "number"
      ) {
        callbacks.onMeta?.({
          items: estado.meta.items,
          tareas: estado.meta.tareas ?? 0,
        });
        metaEnviada = true;
      }
      if (estado.texto.length > visto) {
        callbacks.onToken(estado.texto.slice(visto));
        visto = estado.texto.length;
      }
      if (estado.estado === "fin") break;
      if (estado.estado === "error") {
        throw new ErrorApi(500, estado.detalle ?? "Error del asistente");
      }
    }
  },

  /** POST /api/shopping-list: añade una entrada manual a la compra. */
  anadirAListaCompra: (
    nombre: string,
    cantidad?: number,
    unidad?: string,
    categoria?: string,
  ) =>
    post<{ anadido: boolean; item_id: string | null; nombre: string }>(
      "/api/shopping-list",
      { nombre, cantidad, unidad, categoria },
    ),
};
