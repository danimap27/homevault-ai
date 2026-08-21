/**
 * Tipos TypeScript que reflejan los modelos Pydantic v2 de
 * `backend/models.py`. Mantener sincronizados con el backend.
 */

// --- Catálogos (Literals del backend) ----------------------------------------

export type CategoriaItem =
  | "lacteos"
  | "congelados"
  | "despensa_seca"
  | "limpieza"
  | "recambios_hogar"
  | "botiquin";

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
  tags: string[];
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
