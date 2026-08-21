"""Modelos Pydantic v2 de HomeVault AI.

Cada modelo refleja EXACTAMENTE el esquema YAML frontmatter definido en la
especificación de Fase 1. Los modelos son la validación estricta de la única
fuente de verdad: los archivos Markdown del vault.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# --- Catálogos de valores permitidos -----------------------------------------

CategoriaItem = Literal[
    "lacteos", "congelados", "despensa_seca", "limpieza",
    "recambios_hogar", "botiquin",
]
Ubicacion = Literal["nevera", "congelador", "despensa", "bano", "trastero"]
Unidad = Literal["litros", "kg", "gramos", "unidades", "pastillas", "dosis"]
CategoriaReceta = Literal["desayuno", "comida", "cena", "snack"]
Frecuencia = Literal[
    "unica", "diaria", "semanal", "quincenal", "mensual",
    "cada_3_meses", "cada_6_meses", "anual",
]
EstadoTarea = Literal["pendiente", "completada"]
Prioridad = Literal["baja", "media", "alta", "urgente"]


# --- A. Consumible (inventario/**.md) ----------------------------------------


class Lote(BaseModel):
    """Lote FIFO de un consumible."""

    id_lote: str
    cantidad: float
    fecha_caducidad: Optional[date] = None
    fecha_adquisicion: Optional[date] = None


class Consumible(BaseModel):
    """Esquema A: ítem de inventario (inventario/**.md)."""

    id: str
    nombre: str
    ean_barcode: Optional[str] = None
    categoria: CategoriaItem
    ubicacion: Ubicacion
    stock_actual: float = 0.0
    stock_minimo: float = 0.0
    unidad: Unidad
    precio_unitario_estimado: Optional[float] = None
    fecha_caducidad_proxima: Optional[date] = None
    fecha_congelacion: Optional[date] = None
    dias_max_congelador: Optional[int] = None
    lotes: list[Lote] = Field(default_factory=list)
    es_reserva_estrategica: bool = False
    mqtt_sensor_topic: Optional[str] = None
    dias_promedio_consumo: Optional[float] = None
    ultimo_consumo: Optional[datetime] = None
    auto_lista_compra: bool = False
    tags: list[str] = Field(default_factory=list)
    ultima_actualizacion: Optional[datetime] = None


# --- B. Receta (recetas/*.md) ------------------------------------------------


class Ingrediente(BaseModel):
    """Ingrediente de una receta."""

    item_id: Optional[str] = None
    nombre: str
    cantidad: float
    unidad: str


class Receta(BaseModel):
    """Esquema B: receta (recetas/*.md)."""

    id: str
    titulo: str
    categoria: CategoriaReceta
    tiempo_minutos: int
    raciones: int
    calorias_racion: Optional[int] = None
    ingredientes: list[Ingrediente] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


# --- C. Planificador semanal (planificador/YYYY-Www.md) -----------------------


class ComidaPlanificada(BaseModel):
    """Slot de comida/cena de un día del planificador."""

    receta_id: Optional[str] = None
    plato_libre: Optional[str] = None
    raciones: Optional[int] = None
    stock_deducido: bool = False


class BatchCooking(BaseModel):
    """Sesión de batch cooking programada."""

    fecha: date
    recetas_a_preparar: list[str] = Field(default_factory=list)
    destino_inventario: Optional[str] = None


class PlanSemanal(BaseModel):
    """Esquema C: planificador semanal (planificador/YYYY-Www.md)."""

    semana_iso: str
    fecha_inicio: date
    fecha_fin: date
    dias: dict[str, dict[str, ComidaPlanificada]] = Field(default_factory=dict)
    batch_cooking_programado: list[BatchCooking] = Field(default_factory=list)


# --- D. Tarea doméstica (tareas/*.md) -----------------------------------------


class ConsumibleRequerido(BaseModel):
    """Consumible que una tarea necesita del inventario."""

    item_id: str
    cantidad: float
    unidad: Unidad
    verificar_stock_previo: bool = False


class HistorialCompletado(BaseModel):
    """Registro de una realización pasada de la tarea."""

    fecha: date
    usuario: Optional[str] = None


class Tarea(BaseModel):
    """Esquema D: tarea doméstica (tareas/*.md)."""

    id: str
    titulo: str
    zona: Optional[str] = None
    frecuencia: Frecuencia = "unica"
    estado: EstadoTarea = "pendiente"
    asignado_a: Optional[str] = None
    rotacion_convivientes: list[str] = Field(default_factory=list)
    indice_rotacion_actual: int = 0
    prioridad: Prioridad = "media"
    consumibles_requeridos: list[ConsumibleRequerido] = Field(
        default_factory=list
    )
    google_task_id: Optional[str] = None
    google_calendar_event_id: Optional[str] = None
    fecha_programada: Optional[date] = None
    ultima_realizacion: Optional[datetime] = None
    historial_completados: list[HistorialCompletado] = Field(
        default_factory=list
    )
    bloqueada_por_stock: bool = False


# --- Resultados de operaciones del VaultManager -------------------------------


class ResultadoConsumo(BaseModel):
    """Resultado de consume_item()."""

    item_id: str
    cantidad_solicitada: float
    cantidad_consumida_lotes: float
    cantidad_consumida_stock: float
    stock_actual: float
    stock_minimo: float
    bajo_minimo: bool
    anadido_a_lista_compra: bool


class ResultadoCompra(BaseModel):
    """Resultado de add_purchase()."""

    item_id: str
    id_lote: str
    cantidad: float
    stock_actual: float
    tachado_de_lista_compra: bool


class ItemHuerfano(BaseModel):
    """Ítem candidato a revisión por falta de consumo."""

    item_id: str
    nombre: str
    dias_desde_ultimo_consumo: float
    dias_exceso: float


class ItemCaducidad(BaseModel):
    """Ítem próximo a caducar."""

    item_id: str
    nombre: str
    fecha_caducidad: date
    dias_restantes: int
    origen: str  # "item" o id del lote


class EntradaListaCompra(BaseModel):
    """Entrada parseada de listas/compra.md."""

    item_id: str
    nombre: str
    cantidad: Optional[float] = None
    unidad: Optional[str] = None
    categoria: Optional[str] = None
    comprado: bool = False


# --- E. Perfil de usuario (vault/config/perfiles.json) ------------------------


class Perfil(BaseModel):
    """Esquema E: perfil de usuario estilo Netflix."""

    id: str
    nombre: str
    avatar: str = "👤"
    color: str = "#6366f1"
    pin: Optional[str] = None
    preferencias: dict = Field(default_factory=dict)


# --- F. Vista de calendario de tareas -----------------------------------------


class VistaCalendarioTarea(BaseModel):
    """Ocurrencia de una tarea en la vista de calendario."""

    task_id: str
    titulo: str
    fecha: date
    estado: EstadoTarea
    prioridad: Prioridad
    asignado_a: Optional[str] = None
    bloqueada_por_stock: bool = False
