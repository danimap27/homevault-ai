/**
 * Tipos TypeScript que reflejan los modelos Pydantic v2 de
 * `backend/models.py`. Mantener sincronizados con el backend.
 */

// --- Catálogos (Literals del backend) ----------------------------------------

/** Identificador de categoría dinámica. Antes era un Literal cerrado; ahora el
 *  backend permite crear categorías arbitrarias vía `/api/categories`. */
export type CategoriaItem = string;

export interface Categoria {
  id: string;
  nombre: string;
  color: string;
  icono: string;
  ubicacion_default: string | null;
  orden: number;
}

export type Ubicacion = "nevera" | "congelador" | "despensa" | "bano" | "trastero";

export type Unidad =
  | "litros"
  | "kg"
  | "gramos"
  | "unidades"
  | "pastillas"
  | "dosis";

export type CategoriaReceta = "desayuno" | "comida" | "cena" | "snack";

export type Prioridad = "baja" | "media" | "alta" | "urgente";

export type EstadoTarea = "pendiente" | "completada";

// --- Perfiles -----------------------------------------------------------------

export interface PreferenciasPerfil {
  vista_calendario_preferida?: "dia" | "semana" | "mes";
  notificaciones?: boolean;
  [clave: string]: unknown;
}

export interface Perfil {
  id: string;
  nombre: string;
  avatar: string | null;
  color: string | null;
  pin: string | null;
  preferencias: PreferenciasPerfil | null;
}

export interface CrearPerfilInput {
  id?: string;
  nombre: string;
  avatar?: string | null;
  color?: string | null;
  pin?: string | null;
  preferencias?: PreferenciasPerfil | null;
}

// --- Inventario ---------------------------------------------------------------

export interface Lote {
  id_lote: string;
  cantidad: number;
  fecha_caducidad: string | null;
  fecha_adquisicion: string | null;
  supermercado: string | null;
}

export interface Consumible {
  id: string;
  nombre: string;
  ean_barcode: string | null;
  categoria: CategoriaItem;
  ubicacion: Ubicacion;
  stock_actual: number;
  stock_minimo: number;
  unidad: Unidad;
  precio_unitario_estimado: number | null;
  fecha_caducidad_proxima: string | null;
  fecha_congelacion: string | null;
  dias_max_congelador: number | null;
  lotes: Lote[];
  es_reserva_estrategica: boolean;
  mqtt_sensor_topic: string | null;
  dias_promedio_consumo: number | null;
  ultimo_consumo: string | null;
  auto_lista_compra: boolean;
  tags: string[];
  ultima_actualizacion: string | null;
}

export interface ItemCaducidad {
  item_id: string;
  nombre: string;
  fecha_caducidad: string;
  dias_restantes: number;
  origen: string;
}

export interface ResultadoConsumo {
  item_id: string;
  cantidad_solicitada: number;
  cantidad_consumida_lotes: number;
  cantidad_consumida_stock: number;
  stock_actual: number;
  stock_minimo: number;
  bajo_minimo: boolean;
  anadido_a_lista_compra: boolean;
}

export interface ResultadoCompra {
  item_id: string;
  id_lote: string;
  cantidad: number;
  stock_actual: number;
  tachado_de_lista_compra: boolean;
  supermercado: string | null;
}

// --- Recetas y planificador ----------------------------------------------------

export interface Ingrediente {
  item_id: string | null;
  nombre: string;
  cantidad: number;
  unidad: string;
}

export interface Receta {
  id: string;
  titulo: string;
  categoria: CategoriaReceta;
  tiempo_minutos: number;
  raciones: number;
  calorias_racion: number | null;
  ingredientes: Ingrediente[];
  instrucciones: string | null;
  tags: string[];
}

export interface IngredienteFaltante {
  nombre: string;
  cantidad_necesaria: number;
  cantidad_disponible: number;
  unidad: string;
}

export interface RecetaPosible {
  receta: Receta;
  score: number;
  posible_completa: boolean;
  faltantes: IngredienteFaltante[];
}

export interface CrearRecetaInput {
  id?: string;
  titulo: string;
  categoria: CategoriaReceta;
  tiempo_minutos?: number;
  raciones?: number;
  calorias_racion?: number | null;
  ingredientes?: Ingrediente[];
  instrucciones?: string | null;
  tags?: string[];
}

export interface ActualizarRecetaInput {
  titulo?: string;
  categoria?: CategoriaReceta;
  tiempo_minutos?: number;
  raciones?: number;
  calorias_racion?: number | null;
  ingredientes?: Ingrediente[];
  instrucciones?: string | null;
  tags?: string[];
}

export interface CrearConsumibleInput {
  id?: string;
  nombre: string;
  categoria: CategoriaItem;
  ubicacion: Ubicacion;
  stock_minimo?: number;
  unidad: Unidad;
  precio_unitario_estimado?: number | null;
  ean_barcode?: string | null;
  auto_lista_compra?: boolean;
  tags?: string[];
}

export interface ActualizarConsumibleInput {
  nombre?: string;
  categoria?: CategoriaItem;
  ubicacion?: Ubicacion;
  stock_minimo?: number;
  unidad?: Unidad;
  precio_unitario_estimado?: number | null;
  ean_barcode?: string | null;
  auto_lista_compra?: boolean;
  tags?: string[];
}

export interface MoverItemInput {
  categoria?: CategoriaItem;
  ubicacion?: Ubicacion;
}

export interface CocinarRecetaInput {
  raciones?: number;
}

export interface CocinarRecetaResultado {
  receta_id: string;
  raciones: number;
  consumidos: { item_id: string | null; nombre: string; cantidad: number; unidad: string }[];
  faltantes: IngredienteFaltante[];
  anadidos_a_lista_compra: { item_id: string | null; nombre: string; cantidad: number; unidad: string }[];
}

export interface AsignarPlanInput {
  semana_iso: string;
  dia: string;
  toma: string;
  receta_id: string;
  raciones: number;
}

export interface ComidaPlanificada {
  receta_id: string | null;
  plato_libre: string | null;
  raciones: number | null;
  stock_deducido: boolean;
}

export interface BatchCooking {
  fecha: string;
  recetas_a_preparar: string[];
  destino_inventario: string | null;
}

export interface PlanSemanal {
  semana_iso: string;
  fecha_inicio: string;
  fecha_fin: string;
  dias: Record<string, Record<string, ComidaPlanificada>>;
  batch_cooking_programado: BatchCooking[];
}

// --- Tareas ---------------------------------------------------------------------

export interface ConsumibleRequerido {
  item_id: string;
  cantidad: number;
  unidad: Unidad;
  verificar_stock_previo: boolean;
}

export interface HistorialCompletado {
  fecha: string;
  usuario: string | null;
}

export interface Tarea {
  id: string;
  titulo: string;
  zona: string | null;
  frecuencia: string;
  estado: EstadoTarea;
  asignado_a: string | null;
  rotacion_convivientes: string[];
  indice_rotacion_actual: number;
  prioridad: Prioridad;
  consumibles_requeridos: ConsumibleRequerido[];
  google_task_id: string | null;
  google_calendar_event_id: string | null;
  fecha_programada: string | null;
  ultima_realizacion: string | null;
  historial_completados: HistorialCompletado[];
  bloqueada_por_stock: boolean;
}

export interface CrearTareaInput {
  titulo: string;
  zona?: string | null;
  frecuencia?: string;
  estado?: EstadoTarea;
  asignado_a?: string | null;
  rotacion_convivientes?: string[];
  indice_rotacion_actual?: number;
  prioridad?: Prioridad;
  consumibles_requeridos?: ConsumibleRequerido[];
  fecha_programada?: string | null;
}

export interface ActualizarTareaInput {
  titulo?: string;
  zona?: string | null;
  frecuencia?: string;
  estado?: EstadoTarea;
  asignado_a?: string | null;
  rotacion_convivientes?: string[];
  indice_rotacion_actual?: number;
  prioridad?: Prioridad;
  consumibles_requeridos?: ConsumibleRequerido[];
  fecha_programada?: string | null;
}

export interface VistaCalendarioTarea {
  task_id: string;
  titulo: string;
  fecha: string;
  estado: EstadoTarea;
  prioridad: Prioridad;
  asignado_a: string | null;
  bloqueada_por_stock: boolean;
}

// --- Lista de la compra -----------------------------------------------------------

export interface EntradaListaCompra {
  item_id: string;
  nombre: string;
  cantidad: number | null;
  unidad: string | null;
  categoria: string | null;
  comprado: boolean;
}

// --- Respuestas de endpoints del planner, impresión y finanzas -----------------

/** Respuesta de GET /api/finance/summary. */
export interface ResumenFinanciero {
  mes: string; // "YYYY-MM"
  total: number;
  por_categoria: { categoria: string; total: number }[];
}

/** Sugerencia del Rescue Chef (GET /api/planner/rescue). */
export interface SugerenciaRescate {
  receta: Receta;
  items_a_rescatar: ItemCaducidad[];
  dias_restantes_min: number;
  stock_critico: boolean;
}

/** Ingrediente descontado en el batch cooking (backend/planner.py). */
export interface IngredienteBatch {
  item_id: string | null;
  nombre: string;
  cantidad: number;
  unidad: string;
  consumido: boolean;
  detalle: string;
}

/** Tupper creado por el batch cooking (backend/planner.py). */
export interface TupperCreado {
  receta_id: string;
  titulo: string;
  item_id: string;
  ruta: string;
  raciones: number;
  fecha_congelacion: string;
  fecha_caducidad: string;
}

/** Respuesta de POST /api/planner/batch-cooking. */
export interface ResultadoBatchCooking {
  destino: string;
  tuppers: TupperCreado[];
  ingredientes: IngredienteBatch[];
}

/** Respuesta de POST /api/print/receipt-list y /api/print/label-tupper. */
export interface ResultadoImpresion {
  impreso: boolean;
  lineas: number;
}

/** Respuesta de POST /api/shopping-list/check. */
export interface RespuestaCheckLista {
  item_id: string;
  tachadas: number;
}

/** Supermercado (backend/supermercados.py). */
export interface Supermercado {
  id: string;
  nombre: string;
  predeterminado: boolean;
}

/** Código de barras local (backend/local_barcodes.py). */
export interface LocalBarcode {
  ean: string;
  nombre: string;
  categoria: CategoriaItem;
  ubicacion: Ubicacion;
  unidad: Unidad;
  supermercado: string | null;
  precio_unitario_estimado: number | null;
  tags: string[];
}

/** Respuesta de DELETE /api/shopping-list/{item_id}. */
export interface RespuestaBorrarLista {
  item_id: string;
  eliminadas: number;
}

/** Respuesta de PUT /api/shopping-list/{item_id}. */
export interface RespuestaEditarLista {
  item_id: string;
  editadas: number;
}

// --- Inteligencia del hogar (Fase 7) -------------------------------------------

/** Motivos válidos de una merma (Literal del backend). */
export type MotivoMerma = "caducado" | "estropeado" | "no_deseado" | "otro";

export type UrgenciaReposicion = "critica" | "alta" | "media";

export type ConfianzaPrediccion = "alta" | "media" | "baja";

/** Predicción de agotamiento de un ítem (GET /api/insights/predictions). */
export interface PrediccionAgotamiento {
  item_id: string;
  nombre: string;
  unidad: Unidad;
  disponible: number;
  tasa_diaria: number;
  dias_restantes: number;
  fecha_estimada_agotamiento: string;
  confianza: ConfianzaPrediccion;
}

/** Sugerencia de reposición priorizada (GET /api/insights/restock). */
export interface SugerenciaReposicion {
  item_id: string;
  nombre: string;
  categoria: CategoriaItem;
  ubicacion: Ubicacion;
  unidad: Unidad;
  disponible: number;
  stock_minimo: number;
  dias_restantes: number | null;
  urgencia: UrgenciaReposicion;
  motivo: string;
  ya_en_lista: boolean;
  precio_estimado: number | null;
}

/** Registro de desperdicio (merma) de un mes. */
export interface DesperdicioRegistrado {
  fecha: string;
  item_id: string;
  nombre: string;
  cantidad: number;
  unidad: Unidad;
  motivo: string;
  valor_estimado: number;
}

/** Resumen mensual de desperdicio (GET /api/insights/waste). */
export interface ResumenDesperdicio {
  mes: string;
  total_registros: number;
  valor_total: number;
  por_motivo: Record<string, number>;
  ultimos: DesperdicioRegistrado[];
}

/** Cuota de tareas completadas por conviviente (equidad). */
export interface CuotaConviviente {
  nombre: string;
  completadas: number;
  porcentaje: number;
}

/** Tarea pendiente con fecha pasada. */
export interface TareaVencida {
  task_id: string;
  titulo: string;
  fecha_programada: string | null;
  dias_retraso: number;
  asignado_a: string | null;
  prioridad: Prioridad;
}

/** Estadísticas de tareas (GET /api/insights/tasks). */
export interface EstadisticasTareas {
  mes: string;
  completadas_mes: number;
  por_conviviente: CuotaConviviente[];
  pendientes: number;
  vencidas: number;
  proximas_7_dias: number;
  completadas_30d: number;
  a_tiempo_30d: number | null;
  top_vencidas: TareaVencida[];
}

/** Panel de inteligencia completo (GET /api/insights). */
export interface ResumenInteligencia {
  fecha: string;
  valor_inventario: number;
  total_items: number;
  items_bajo_minimo: number;
  caducidades_7_dias: number;
  reposicion: SugerenciaReposicion[];
  predicciones: PrediccionAgotamiento[];
  desperdicio_mes: ResumenDesperdicio;
  tareas: EstadisticasTareas;
}

/** Respuesta de POST /api/inventory/{item_id}/waste. */
export interface ResultadoDesperdicio {
  item_id: string;
  nombre: string;
  cantidad: number;
  stock_actual: number;
  valor_estimado: number;
  resumen_mes: ResumenDesperdicio;
}

/** Respuesta del asistente del hogar (POST /api/ai/chat). */
export interface RespuestaChat {
  respuesta: string;
  items_en_contexto: number;
  tareas_en_contexto: number;
}
