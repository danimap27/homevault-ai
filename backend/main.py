"""API FastAPI de HomeVault AI.

Fase 1: endpoints REST de inventario apoyados en VaultManager.
Fase 2: endpoints de tareas y sincronización con Google Workspace.
Fase 3: ingesta multimodal de tickets con ReceiptParser.
Fase 4: domótica (MQTT + webhooks), escaneo de códigos de barras, planner de
cocina, impresión ESC/POS/NFC, observador del vault con WebSockets y
auto-sincronización Git (routers en backend/routers/).
Fase 5: endpoints de recetas, plan semanal y resumen financiero para el
frontend Next.js, con CORS configurable.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Optional

from dateutil.relativedelta import relativedelta
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from backend.ai_vision_parser import (
    ErrorParseoTicket,
    GastoMes,
    ReceiptParser,
    ResultadoRegistroCompra,
    build_llm_client,
)
from backend.categorias import Categoria, CategoriaManager
from backend.config import get_settings
from backend.git_sync import GitSync
from backend.google_sync import GoogleSync, build_google_sync
from backend.local_barcodes import LocalBarcode, LocalBarcodeManager
from backend.models import (
    Consumible,
    ConsumibleRequerido,
    EntradaListaCompra,
    Frecuencia,
    Ingrediente,
    IngredienteFaltante,
    ItemCaducidad,
    ItemHuerfano,
    Perfil,
    PlanSemanal,
    Prioridad,
    Receta,
    RecetaPosible,
    ResultadoCompra,
    ResultadoConsumo,
    Tarea,
    VistaCalendarioTarea,
)
from backend.mqtt_connector import MQTTConnector, build_mqtt_connector
from backend.off_client import OFFClient, build_off_client
from backend.printer import build_printer
from backend.routers import (
    barcode,
    domotica,
    planner,
    print_nfc,
    ws,
)
from backend.perfiles import PerfilManager
from backend.planner import (
    InsufficientStockError,
    Planner,
    ResultadoAsignarPlan,
    ResultadoCocinarReceta,
)
from backend.supermercados import Supermercado, SupermercadoManager
from backend.vault_manager import VaultManager
from backend.watcher import VaultWatcher, WebSocketManager

logger = logging.getLogger(__name__)

# Formato estricto de los identificadores temporales usados en rutas de archivo
_REGEX_SEMANA_ISO = re.compile(r"^\d{4}-W\d{2}$")
_REGEX_MES = re.compile(r"^\d{4}-\d{2}$")


class PeticionConsumo(BaseModel):
    """Cuerpo de POST /api/inventory/consume."""

    item_id_o_nombre: str
    cantidad: float = Field(gt=0)


class PeticionCompra(BaseModel):
    """Cuerpo de POST /api/inventory/purchase."""

    item_id_o_nombre: str
    cantidad: float = Field(gt=0)
    precio_unitario: float = Field(ge=0)
    fecha_caducidad: Optional[date] = None
    supermercado: Optional[str] = None


class PeticionCompletarTarea(BaseModel):
    """Cuerpo de POST /api/tasks/{task_id}/complete."""

    completed_by: Optional[str] = None


class CrearTarea(BaseModel):
    """Cuerpo de POST /api/tasks."""

    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = None
    titulo: str
    zona: Optional[str] = None
    frecuencia: Frecuencia = "unica"
    prioridad: Prioridad = "media"
    asignado_a: Optional[str] = None
    rotacion_convivientes: Optional[list[str]] = None
    fecha_programada: Optional[date] = None
    consumibles_requeridos: list[ConsumibleRequerido] = Field(
        default_factory=list
    )
    indice_rotacion_actual: int = 0


class ActualizarTarea(BaseModel):
    """Cuerpo de PUT /api/tasks/{task_id}."""

    titulo: Optional[str] = None
    zona: Optional[str] = None
    frecuencia: Optional[Frecuencia] = None
    prioridad: Optional[Prioridad] = None
    asignado_a: Optional[str] = None
    rotacion_convivientes: Optional[list[str]] = None
    fecha_programada: Optional[date] = None
    consumibles_requeridos: Optional[list[ConsumibleRequerido]] = None
    indice_rotacion_actual: Optional[int] = None


class CrearPerfil(BaseModel):
    """Cuerpo de POST /api/profiles."""

    id: str
    nombre: str
    avatar: str = "👤"
    color: Optional[str] = None
    pin: Optional[str] = None
    preferencias: dict = Field(default_factory=dict)


class ActualizarPerfil(BaseModel):
    """Cuerpo de PUT /api/profiles/{id}."""

    nombre: Optional[str] = None
    avatar: Optional[str] = None
    color: Optional[str] = None
    pin: Optional[str] = None
    preferencias: Optional[dict] = None


class PeticionVerificarPin(BaseModel):
    """Cuerpo de POST /api/profiles/{id}/verify-pin."""

    pin: str = ""


class PeticionTicketTexto(BaseModel):
    """Cuerpo JSON de POST /api/ingest/receipt (ticket en texto)."""

    texto: str
    comercio: Optional[str] = None
    total: Optional[float] = Field(default=None, ge=0)
    supermercado: Optional[str] = None


async def _bucle_polling(sync: GoogleSync, intervalo_s: int) -> None:
    """Bucle de polling de Google Tasks con el intervalo configurado."""
    while True:
        try:
            await sync.poll_google_tasks()
        except Exception:
            logger.exception("Error en el polling de Google Tasks")
        await asyncio.sleep(intervalo_s)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Instancia VaultManager y los servicios opcionales de las Fases 2-4."""
    settings = get_settings()
    vault = VaultManager(settings.vault_path)
    app.state.vault = vault

    sync: Optional[GoogleSync] = None
    if settings.google_sync_enabled:
        try:
            sync = build_google_sync(vault, settings)
        except Exception:
            logger.exception(
                "No se pudo inicializar GoogleSync; la API sigue sin sync remoto"
            )
    if sync is None:
        # Fallback: lógica local de tareas sin clientes remotos
        sync = GoogleSync(
            vault,
            tasks_list_id=settings.google_tasks_list_id,
            calendar_id=settings.google_calendar_id,
        )
    app.state.google_sync = sync

    parser: Optional[ReceiptParser] = None
    if settings.ai_provider:
        try:
            parser = ReceiptParser(vault, build_llm_client(settings))
        except Exception:
            logger.exception(
                "No se pudo inicializar el cliente LLM; /api/ingest "
                "responderá 503"
            )
    app.state.receipt_parser = parser

    # Gestor de WebSockets y observador del vault (Fase 4)
    ws_manager = WebSocketManager()
    app.state.ws_manager = ws_manager

    watcher: Optional[VaultWatcher] = None
    if settings.watcher_enabled:
        watcher = VaultWatcher(settings.vault_path)
        watcher.suscribir(
            lambda evento: ws_manager.broadcast(evento.a_json())
        )
        await watcher.start()
    app.state.watcher = watcher

    # Auto-sincronización Git del vault (degrada si no hay repo)
    app.state.git_sync = GitSync(
        settings.vault_path,
        debounce_s=settings.git_debounce_s,
        remote_enabled=settings.git_remote_enabled,
    )

    # Cliente de Open Food Facts para el escaneo de códigos de barras
    off_client: OFFClient = build_off_client()
    app.state.off_client = off_client

    # Impresora térmica ESC/POS (opcional; sin host el router responde 503)
    app.state.printer = (
        build_printer(settings.printer_host, settings.printer_port)
        if settings.printer_host
        else None
    )

    # Conector MQTT + Home Assistant (Fase 4a)
    mqtt: Optional[MQTTConnector] = None
    if settings.mqtt_enabled:
        try:
            mqtt = build_mqtt_connector(vault, settings, google_sync=sync)
            await mqtt.start()
        except Exception:
            logger.exception(
                "No se pudo iniciar el conector MQTT; la API sigue sin domótica"
            )
            mqtt = None
    app.state.mqtt_connector = mqtt

    tarea_poll: Optional[asyncio.Task] = None
    if settings.google_sync_enabled and sync.tasks_client is not None:
        tarea_poll = asyncio.create_task(
            _bucle_polling(sync, settings.google_poll_interval_s)
        )
    try:
        yield
    finally:
        if tarea_poll is not None:
            tarea_poll.cancel()
            try:
                await tarea_poll
            except asyncio.CancelledError:
                pass
        if mqtt is not None:
            await mqtt.stop()
        await off_client.aclose()
        if watcher is not None:
            await watcher.stop()


app = FastAPI(title="HomeVault AI", version="0.5.0", lifespan=lifespan)

# CORS para el frontend Next.js (orígenes configurables vía CORS_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers de la Fase 4 (domótica, barcode, planner, impresión/NFC y WebSocket)
app.include_router(domotica.router)
app.include_router(barcode.router)
app.include_router(planner.router)
app.include_router(print_nfc.router)
app.include_router(ws.router)


def _vault(request: Request) -> VaultManager:
    """Recupera el VaultManager del estado de la app."""
    return request.app.state.vault


def _categoria_manager(request: Request) -> CategoriaManager:
    """Recupera el gestor de categorías desde el VaultManager de la app."""
    return request.app.state.vault.categoria_manager


def _planner(request: Request) -> Planner:
    """Construye el Planner sobre el VaultManager de la petición."""
    return Planner(_vault(request))


def _sync(request: Request) -> GoogleSync:
    """Recupera el GoogleSync del estado de la app."""
    return request.app.state.google_sync


def _perfil_manager(request: Request) -> PerfilManager:
    """Crea un PerfilManager ligado al vault actual de la petición.

    No se cachea en ``app.state`` para evitar que los tests con vaults
    temporales compartan el mismo manager entre ejecuciones.
    """
    return PerfilManager(request.app.state.vault.vault_path)


def _supermercado_manager(request: Request) -> SupermercadoManager:
    """Crea un SupermercadoManager ligado al vault actual de la petición."""
    return SupermercadoManager(request.app.state.vault.vault_path)


def _local_barcode_manager(request: Request) -> LocalBarcodeManager:
    """Crea un LocalBarcodeManager ligado al vault actual de la petición."""
    return LocalBarcodeManager(request.app.state.vault.vault_path)


def _slugify(texto: str) -> str:
    """Convierte un título en un slug seguro para nombre de archivo."""
    slug = re.sub(r"[^\w\s-]", "", texto.lower().strip())
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug or "tarea"


# Deltas para la generación de ocurrencias del calendario
_DELTAS_CALENDARIO: dict[Frecuencia, relativedelta | timedelta] = {
    "diaria": timedelta(days=1),
    "semanal": timedelta(weeks=1),
    "quincenal": timedelta(weeks=2),
    "mensual": relativedelta(months=+1),
    "cada_3_meses": relativedelta(months=+3),
    "cada_6_meses": relativedelta(months=+6),
    "anual": relativedelta(years=+1),
}


def _ocurrencias_tarea_en_rango(
    tarea: Tarea, desde: date, hasta: date
) -> list[VistaCalendarioTarea]:
    """Genera las vistas de calendario de una tarea dentro del rango.

    Para tareas recurrentes genera ocurrencias desde ``desde`` hasta ``hasta``.
    Para tareas únicas devuelve una sola ocurrencia si la fecha cae en rango.
    """
    if tarea.fecha_programada is None:
        return []

    delta = _DELTAS_CALENDARIO.get(tarea.frecuencia)
    if delta is None:
        # Tarea única
        if desde <= tarea.fecha_programada <= hasta:
            return [_vista_calendario(tarea, tarea.fecha_programada)]
        return []

    ocurrencias: list[VistaCalendarioTarea] = []
    fecha = tarea.fecha_programada
    # Avanzar hasta el primer día dentro del rango para no iterar sin límite
    while fecha < desde:
        fecha = _sumar_frecuencia(fecha, delta)

    while fecha <= hasta:
        ocurrencias.append(_vista_calendario(tarea, fecha))
        fecha = _sumar_frecuencia(fecha, delta)

    return ocurrencias


def _sumar_frecuencia(fecha: date, delta: relativedelta | timedelta) -> date:
    """Suma un delta a una fecha y devuelve un date."""
    resultado = fecha + delta
    if isinstance(resultado, datetime):
        return resultado.date()
    return resultado


def _vista_calendario(tarea: Tarea, fecha: date) -> VistaCalendarioTarea:
    """Construye una ``VistaCalendarioTarea`` a partir de una tarea y fecha."""
    return VistaCalendarioTarea(
        task_id=tarea.id,
        titulo=tarea.titulo,
        fecha=fecha,
        estado=tarea.estado,
        prioridad=tarea.prioridad,
        asignado_a=tarea.asignado_a,
        bloqueada_por_stock=tarea.bloqueada_por_stock,
    )


@app.get("/api/inventory", response_model=list[Consumible])
async def listar_inventario(
    request: Request, ubicacion: Optional[str] = None
) -> list[Consumible]:
    """Lista completa del inventario, con filtro opcional por ubicación."""
    return await _vault(request).list_items(ubicacion=ubicacion)


@app.get("/api/inventory/expiring", response_model=list[ItemCaducidad])
async def inventario_por_caducar(
    request: Request, days_ahead: int = Query(default=4, ge=0)
) -> list[ItemCaducidad]:
    """Ítems que caducan dentro de days_ahead días, ordenados por urgencia."""
    return await _vault(request).query_expiring(days_ahead)


@app.get("/api/inventory/orphans", response_model=list[ItemHuerfano])
async def inventario_huerfanos(request: Request) -> list[ItemHuerfano]:
    """Ítems candidatos a revisión por falta de consumo."""
    return await _vault(request).find_orphan_items()


@app.post("/api/inventory/consume", response_model=ResultadoConsumo)
async def consumir_item(
    request: Request, peticion: PeticionConsumo
) -> ResultadoConsumo:
    """Consume unidades de un ítem (FIFO por lotes)."""
    vault = _vault(request)
    item = await vault.resolve_item(peticion.item_id_o_nombre)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ítem no encontrado: {peticion.item_id_o_nombre}",
        )
    return await vault.consume_item(item.id, peticion.cantidad)


@app.post("/api/inventory/purchase", response_model=ResultadoCompra)
async def registrar_compra(
    request: Request, peticion: PeticionCompra
) -> ResultadoCompra:
    """Registra una compra: nuevo lote e incremento de stock."""
    vault = _vault(request)
    item = await vault.resolve_item(peticion.item_id_o_nombre)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ítem no encontrado: {peticion.item_id_o_nombre}",
        )
    return await vault.add_purchase(
        item.id,
        peticion.cantidad,
        peticion.precio_unitario,
        peticion.fecha_caducidad,
        supermercado=peticion.supermercado,
    )


@app.get("/api/shopping-list", response_model=list[EntradaListaCompra])
async def lista_compra(request: Request) -> list[EntradaListaCompra]:
    """Contenido parseado de listas/compra.md."""
    return await _vault(request).get_shopping_list()


class PeticionActualizarListaCompra(BaseModel):
    """Cuerpo de PUT /api/shopping-list/{item_id}."""

    cantidad: Optional[float] = None
    unidad: Optional[str] = None
    categoria: Optional[str] = None


@app.delete("/api/shopping-list/{item_id}", status_code=200)
async def borrar_entrada_lista(
    request: Request, item_id: str
) -> dict:
    """Elimina las líneas pendientes de la lista de la compra."""
    eliminadas = await _vault(request).remove_shopping_list_entry(item_id)
    if eliminadas == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Entrada pendiente no encontrada: {item_id}",
        )
    return {"item_id": item_id, "eliminadas": eliminadas}


@app.put("/api/shopping-list/{item_id}")
async def editar_entrada_lista(
    request: Request,
    item_id: str,
    peticion: PeticionActualizarListaCompra,
) -> dict:
    """Edita una línea pendiente existente de la lista de la compra."""
    editadas = await _vault(request).update_shopping_list_entry(
        item_id,
        cantidad=peticion.cantidad,
        unidad=peticion.unidad,
        categoria=peticion.categoria,
    )
    if editadas == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Entrada pendiente no encontrada: {item_id}",
        )
    return {"item_id": item_id, "editadas": editadas}


# --- Ingesta de tickets con IA (Fase 3) -------------------------------------------


@app.post("/api/ingest/receipt", response_model=ResultadoRegistroCompra)
async def ingerir_ticket(request: Request) -> ResultadoRegistroCompra:
    """Ingesta un ticket y lo registra en cascada (inventario + gastos).

    Admite dos formatos: imagen del ticket como multipart/form-data (campos
    "imagen" y opcional "supermercado") o texto en lenguaje natural como JSON
    ({texto, comercio?, total?, supermercado?}).
    """
    parser: Optional[ReceiptParser] = getattr(
        request.app.state, "receipt_parser", None
    )
    if parser is None:
        raise HTTPException(
            status_code=503,
            detail="Proveedor de IA no configurado (AI_PROVIDER)",
        )
    supermercado: Optional[str] = None
    content_type = request.headers.get("content-type", "")
    try:
        if content_type.startswith("multipart/form-data"):
            formulario = await request.form()
            archivo = formulario.get("imagen") or formulario.get("archivo")
            if archivo is None or not hasattr(archivo, "read"):
                raise HTTPException(
                    status_code=400,
                    detail="Falta el campo de imagen en el multipart",
                )
            supermercado_val = formulario.get("supermercado")
            if isinstance(supermercado_val, str):
                supermercado = supermercado_val or None
            ticket = await parser.parse_ticket_from_image(
                await archivo.read(),
                mime_type=archivo.content_type or "image/jpeg",
            )
        else:
            cuerpo = PeticionTicketTexto.model_validate(await request.json())
            supermercado = cuerpo.supermercado
            ticket = await parser.parse_ticket_from_text(
                cuerpo.texto, comercio=cuerpo.comercio, total=cuerpo.total
            )
    except ErrorParseoTicket as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await parser.register_purchase(ticket, supermercado=supermercado)


# --- Tareas y sincronización con Google (Fase 2) --------------------------------


@app.post("/api/tasks/{task_id}/complete", response_model=Tarea)
async def completar_tarea(
    request: Request, task_id: str, peticion: PeticionCompletarTarea
) -> Tarea:
    """Completa una tarea (con verificación previa de consumibles)."""
    sync = _sync(request)
    if await _vault(request).get_task(task_id) is None:
        raise HTTPException(
            status_code=404, detail=f"Tarea no encontrada: {task_id}"
        )
    await sync.check_consumables_before_task(task_id)
    return await sync.complete_task(task_id, peticion.completed_by)


@app.get("/api/tasks/pending", response_model=list[Tarea])
async def tareas_pendientes(
    request: Request, assigned_user: Optional[str] = None
) -> list[Tarea]:
    """Tareas pendientes del vault, con filtro opcional por usuario."""
    return await _vault(request).list_tasks(
        estado="pendiente", asignado_a=assigned_user
    )


@app.post("/api/tasks/{task_id}/check-stock", response_model=Tarea)
async def verificar_stock_tarea(request: Request, task_id: str) -> Tarea:
    """Verifica el stock de los consumibles requeridos por la tarea."""
    try:
        return await _sync(request).check_consumables_before_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/tasks", response_model=list[Tarea])
async def listar_tareas(
    request: Request,
    estado: Optional[str] = None,
    asignado_a: Optional[str] = None,
) -> list[Tarea]:
    """Tareas del vault, con filtros opcionales por estado y asignación."""
    return await _vault(request).list_tasks(estado=estado, asignado_a=asignado_a)


@app.get("/api/tasks/calendar", response_model=list[VistaCalendarioTarea])
async def calendario_tareas(
    request: Request,
    desde: date = Query(alias="from"),
    hasta: date = Query(alias="to"),
) -> list[VistaCalendarioTarea]:
    """Devuelve ocurrencias de tareas en el rango de fechas solicitado."""
    if desde > hasta:
        raise HTTPException(
            status_code=400,
            detail="El parámetro 'from' debe ser anterior o igual a 'to'",
        )
    tareas = await _vault(request).list_tasks()
    ocurrencias: list[VistaCalendarioTarea] = []
    for tarea in tareas:
        ocurrencias.extend(_ocurrencias_tarea_en_rango(tarea, desde, hasta))
    return sorted(ocurrencias, key=lambda v: (v.fecha, v.titulo))


@app.post("/api/tasks", response_model=Tarea, status_code=201)
async def crear_tarea(request: Request, peticion: CrearTarea) -> Tarea:
    """Crea una nueva tarea doméstica en el vault."""
    slug = _slugify(peticion.titulo)
    task_id = peticion.id or f"task_{slug}_{uuid.uuid4().hex[:8]}"

    rotacion = peticion.rotacion_convivientes
    if rotacion is None and peticion.asignado_a:
        rotacion = [peticion.asignado_a]

    tarea = Tarea(
        id=task_id,
        titulo=peticion.titulo,
        zona=peticion.zona,
        frecuencia=peticion.frecuencia,
        estado="pendiente",
        asignado_a=peticion.asignado_a,
        rotacion_convivientes=rotacion or [],
        indice_rotacion_actual=peticion.indice_rotacion_actual,
        prioridad=peticion.prioridad,
        consumibles_requeridos=peticion.consumibles_requeridos,
        fecha_programada=peticion.fecha_programada,
        historial_completados=[],
        bloqueada_por_stock=False,
    )

    try:
        await _vault(request).create_task(tarea, slug=slug)
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe una tarea con el slug '{slug}'",
        ) from exc
    return tarea


@app.get("/api/tasks/{task_id}", response_model=Tarea)
async def obtener_tarea(request: Request, task_id: str) -> Tarea:
    """Devuelve una tarea por su id."""
    tarea = await _vault(request).get_task(task_id)
    if tarea is None:
        raise HTTPException(
            status_code=404, detail=f"Tarea no encontrada: {task_id}"
        )
    return tarea


@app.put("/api/tasks/{task_id}", response_model=Tarea)
async def actualizar_tarea(
    request: Request, task_id: str, peticion: ActualizarTarea
) -> Tarea:
    """Actualiza campos editables de una tarea preservando el cuerpo Markdown."""
    vault = _vault(request)
    path = await vault._find_task_path(task_id)
    if path is None:
        raise HTTPException(
            status_code=404, detail=f"Tarea no encontrada: {task_id}"
        )

    lock = await vault._get_lock(path)
    async with lock:
        tarea, cuerpo = await vault._read_doc(path, Tarea)
        if peticion.titulo is not None:
            tarea.titulo = peticion.titulo
        if peticion.zona is not None:
            tarea.zona = peticion.zona
        if peticion.frecuencia is not None:
            tarea.frecuencia = peticion.frecuencia
        if peticion.prioridad is not None:
            tarea.prioridad = peticion.prioridad
        if peticion.asignado_a is not None:
            tarea.asignado_a = peticion.asignado_a
        if peticion.rotacion_convivientes is not None:
            tarea.rotacion_convivientes = peticion.rotacion_convivientes
        if peticion.fecha_programada is not None:
            tarea.fecha_programada = peticion.fecha_programada
        if peticion.consumibles_requeridos is not None:
            tarea.consumibles_requeridos = peticion.consumibles_requeridos
        if peticion.indice_rotacion_actual is not None:
            tarea.indice_rotacion_actual = peticion.indice_rotacion_actual

        await vault._write_doc(path, tarea, cuerpo)
    return tarea


@app.delete("/api/tasks/{task_id}", status_code=204)
async def borrar_tarea(request: Request, task_id: str) -> None:
    """Elimina el archivo .md de una tarea."""
    borrada = await _vault(request).delete_task(task_id)
    if not borrada:
        raise HTTPException(
            status_code=404, detail=f"Tarea no encontrada: {task_id}"
        )


# --- Lista de la compra: tachado de entradas (Fase 5) -------------------------


class PeticionCheckLista(BaseModel):
    """Cuerpo de POST /api/shopping-list/check."""

    item_id: str


class RespuestaCheckLista(BaseModel):
    """Resultado de tachar una entrada de la lista de la compra."""

    item_id: str
    tachadas: int


@app.post("/api/shopping-list/check", response_model=RespuestaCheckLista)
async def tachar_entrada_lista(
    request: Request, peticion: PeticionCheckLista
) -> RespuestaCheckLista:
    """Tacha ([x]) las líneas pendientes de la lista que coincidan."""
    tachadas = await _vault(request).check_shopping_list_entry(peticion.item_id)
    if tachadas == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Entrada pendiente no encontrada: {peticion.item_id}",
        )
    return RespuestaCheckLista(item_id=peticion.item_id, tachadas=tachadas)


# --- Recetas y plan semanal (Fase 5) ------------------------------------------


@app.get("/api/recipes", response_model=list[Receta])
async def listar_recetas(request: Request) -> list[Receta]:
    """Todas las recetas del vault (recetas/*.md)."""
    return await _vault(request).list_recipes()


def _semana_iso_actual() -> str:
    """Semana ISO actual en formato YYYY-Www."""
    anio, semana, _ = date.today().isocalendar()
    return f"{anio}-W{semana:02d}"


def _validar_semana_iso(semana_iso: str) -> None:
    """Valida el formato YYYY-Www antes de usarlo como nombre de archivo."""
    if not _REGEX_SEMANA_ISO.match(semana_iso):
        raise HTTPException(
            status_code=400,
            detail=f"Semana ISO inválida (formato YYYY-Www): {semana_iso}",
        )


@app.get("/api/planner/current", response_model=PlanSemanal)
async def obtener_plan_actual(request: Request) -> PlanSemanal:
    """Plan de la semana ISO actual (planificador/YYYY-Www.md); 404 si falta."""
    vault = _vault(request)
    semana_iso = _semana_iso_actual()
    ruta = vault.vault_path / "planificador" / f"{semana_iso}.md"
    if not ruta.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No hay plan para la semana {semana_iso}",
        )
    plan, _ = await vault._read_doc(ruta, PlanSemanal)
    return plan


@app.put("/api/planner/current", response_model=PlanSemanal)
async def guardar_plan_actual(request: Request, plan: PlanSemanal) -> PlanSemanal:
    """Guarda el PlanSemanal recibido en planificador/<semana_iso>.md.

    E/S atómica del VaultManager: lock por archivo y escritura con temporal.
    Si el archivo ya existía, se preserva el cuerpo Markdown libre.
    """
    _validar_semana_iso(plan.semana_iso)
    vault = _vault(request)
    ruta = vault.vault_path / "planificador" / f"{plan.semana_iso}.md"
    lock = await vault._get_lock(ruta)
    async with lock:
        cuerpo = f"# Semana {plan.semana_iso}\n"
        if ruta.exists():
            _, cuerpo = await vault._read_doc(ruta, PlanSemanal)
        await vault._write_doc(ruta, plan, cuerpo)
    return plan


# --- Resumen financiero mensual (Fase 5) ---------------------------------------


class TotalCategoria(BaseModel):
    """Total agregado de una categoría de gasto."""

    categoria: str
    total: float


class ResumenFinanciero(BaseModel):
    """Respuesta de GET /api/finance/summary."""

    mes: str  # formato "YYYY-MM"
    total: float
    por_categoria: list[TotalCategoria] = Field(default_factory=list)


async def _categorias_ticket(vault: VaultManager, item_ids: list[str]) -> list[str]:
    """Categorías distintas de los ítems registrados en un ticket."""
    categorias: set[str] = set()
    for item_id in item_ids:
        item = await vault.get_item(item_id)
        if item is not None:
            categorias.add(item.categoria)
    return sorted(categorias)


@app.get("/api/finance/summary", response_model=ResumenFinanciero)
async def resumen_financiero(request: Request, mes: str) -> ResumenFinanciero:
    """Resumen del mes a partir de gastos/YYYY-MM.md.

    Como TicketGasto no guarda categoría propia, el total de cada ticket se
    reparte a partes iguales entre las categorías distintas de los ítems que
    registró; los tickets sin ítems resolubles caen en "otros".
    """
    if not _REGEX_MES.match(mes):
        raise HTTPException(
            status_code=400, detail=f"Mes inválido (formato YYYY-MM): {mes}"
        )
    vault = _vault(request)
    ruta = vault.vault_path / "gastos" / f"{mes}.md"
    if not ruta.exists():
        raise HTTPException(
            status_code=404, detail=f"No hay gastos registrados para {mes}"
        )
    gasto, _ = await vault._read_doc(ruta, GastoMes)

    totales: dict[str, float] = {}
    for ticket in gasto.tickets:
        categorias = await _categorias_ticket(vault, ticket.items_registrados)
        if not categorias:
            categorias = ["otros"]
        parte = round(ticket.total / len(categorias), 2)
        for categoria in categorias:
            totales[categoria] = round(totales.get(categoria, 0.0) + parte, 2)

    return ResumenFinanciero(
        mes=mes,
        total=gasto.total_mes,
        por_categoria=[
            TotalCategoria(categoria=cat, total=tot)
            for cat, tot in sorted(totales.items())
        ],
    )


# --- Perfiles de usuario (estilo Netflix) -------------------------------------


@app.get("/api/profiles", response_model=list[Perfil])
async def listar_perfiles(request: Request) -> list[Perfil]:
    """Lista todos los perfiles del vault."""
    return await _perfil_manager(request).listar()


@app.get("/api/profiles/{perfil_id}", response_model=Perfil)
async def obtener_perfil(request: Request, perfil_id: str) -> Perfil:
    """Devuelve un perfil por su id."""
    perfil = await _perfil_manager(request).obtener(perfil_id)
    if perfil is None:
        raise HTTPException(
            status_code=404, detail=f"Perfil no encontrado: {perfil_id}"
        )
    return perfil


@app.post("/api/profiles", response_model=Perfil, status_code=201)
async def crear_perfil(request: Request, peticion: CrearPerfil) -> Perfil:
    """Crea un nuevo perfil (máximo 8)."""
    try:
        return await _perfil_manager(request).crear(
            perfil_id=peticion.id,
            nombre=peticion.nombre,
            avatar=peticion.avatar,
            color=peticion.color,
            pin=peticion.pin,
            preferencias=peticion.preferencias,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/profiles/{perfil_id}", response_model=Perfil)
async def actualizar_perfil(
    request: Request, perfil_id: str, peticion: ActualizarPerfil
) -> Perfil:
    """Actualiza los campos editables de un perfil."""
    try:
        return await _perfil_manager(request).actualizar(
            perfil_id=perfil_id,
            nombre=peticion.nombre,
            avatar=peticion.avatar,
            color=peticion.color,
            pin=peticion.pin,
            preferencias=peticion.preferencias,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"Perfil no encontrado: {perfil_id}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/profiles/{perfil_id}", status_code=204)
async def borrar_perfil(request: Request, perfil_id: str) -> None:
    """Elimina un perfil si no es el último."""
    try:
        await _perfil_manager(request).borrar(perfil_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"Perfil no encontrado: {perfil_id}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/profiles/{perfil_id}/verify-pin")
async def verificar_pin_perfil(
    request: Request, perfil_id: str, peticion: PeticionVerificarPin
) -> dict:
    """Verifica el PIN de un perfil. Sin PIN siempre válido."""
    try:
        valido = await _perfil_manager(request).verificar_pin(
            perfil_id, peticion.pin
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"Perfil no encontrado: {perfil_id}"
        ) from exc
    return {"valido": valido}


# --- Supermercados -----------------------------------------------------------


class CrearSupermercado(BaseModel):
    """Cuerpo de POST /api/supermarkets."""

    nombre: str


class ActualizarSupermercado(BaseModel):
    """Cuerpo de PUT /api/supermarkets/{id}."""

    nombre: Optional[str] = None
    predeterminado: Optional[bool] = None


@app.get("/api/supermarkets", response_model=list[Supermercado])
async def listar_supermercados(request: Request) -> list[Supermercado]:
    """Lista todos los supermercados del vault."""
    return _supermercado_manager(request).listar()


@app.post("/api/supermarkets", response_model=Supermercado, status_code=201)
async def crear_supermercado(
    request: Request, peticion: CrearSupermercado
) -> Supermercado:
    """Crea un nuevo supermercado."""
    return _supermercado_manager(request).crear(peticion.nombre)


@app.put("/api/supermarkets/{item_id}", response_model=Supermercado)
async def actualizar_supermercado(
    request: Request,
    item_id: str,
    peticion: ActualizarSupermercado,
) -> Supermercado:
    """Actualiza un supermercado existente."""
    try:
        return _supermercado_manager(request).actualizar(
            item_id,
            nombre=peticion.nombre,
            predeterminado=peticion.predeterminado,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"Supermercado no encontrado: {item_id}"
        ) from exc


@app.delete("/api/supermarkets/{item_id}", status_code=204)
async def borrar_supermercado(request: Request, item_id: str) -> None:
    """Elimina un supermercado."""
    borrado = _supermercado_manager(request).borrar(item_id)
    if not borrado:
        raise HTTPException(
            status_code=404, detail=f"Supermercado no encontrado: {item_id}"
        )


# --- Base de datos local de códigos de barras --------------------------------


@app.get("/api/local-barcodes", response_model=list[LocalBarcode])
async def listar_local_barcodes(request: Request) -> list[LocalBarcode]:
    """Lista todos los códigos de barras locales."""
    return _local_barcode_manager(request).listar()


@app.get("/api/local-barcodes/{ean}", response_model=LocalBarcode)
async def obtener_local_barcode(request: Request, ean: str) -> LocalBarcode:
    """Devuelve un código de barras local por su EAN."""
    barcode = _local_barcode_manager(request).obtener(ean)
    if barcode is None:
        raise HTTPException(
            status_code=404, detail=f"Código de barras no encontrado: {ean}"
        )
    return barcode


@app.post("/api/local-barcodes", response_model=LocalBarcode, status_code=201)
async def crear_local_barcode(
    request: Request, barcode: LocalBarcode
) -> LocalBarcode:
    """Crea un nuevo código de barras local."""
    try:
        return _local_barcode_manager(request).crear(barcode)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.put("/api/local-barcodes/{ean}", response_model=LocalBarcode)
async def actualizar_local_barcode(
    request: Request, ean: str, barcode: LocalBarcode
) -> LocalBarcode:
    """Actualiza un código de barras local existente."""
    try:
        return _local_barcode_manager(request).actualizar(
            ean, **barcode.model_dump(exclude={"ean"})
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"Código de barras no encontrado: {ean}"
        ) from exc


@app.delete("/api/local-barcodes/{ean}", status_code=204)
async def borrar_local_barcode(request: Request, ean: str) -> None:
    """Elimina un código de barras local."""
    borrado = _local_barcode_manager(request).borrar(ean)
    if not borrado:
        raise HTTPException(
            status_code=404, detail=f"Código de barras no encontrado: {ean}"
        )


# --- Categorías dinámicas -----------------------------------------------------


class CrearCategoria(BaseModel):
    """Cuerpo de POST /api/categories."""

    id: Optional[str] = None
    nombre: str
    color: Optional[str] = None
    icono: Optional[str] = None
    ubicacion_default: Optional[str] = None
    orden: Optional[int] = None


class ActualizarCategoria(BaseModel):
    """Cuerpo de PUT /api/categories/{id}."""

    nombre: Optional[str] = None
    color: Optional[str] = None
    icono: Optional[str] = None
    ubicacion_default: Optional[str] = None
    orden: Optional[int] = None


class RespuestaBorrarCategoria(BaseModel):
    """Respuesta de DELETE /api/categories/{id}."""

    eliminada: bool
    items_afectados: list[str] = Field(default_factory=list)


@app.get("/api/categories", response_model=list[Categoria])
async def listar_categorias(request: Request) -> list[Categoria]:
    """Lista todas las categorías del vault ordenadas."""
    return _categoria_manager(request).listar()


@app.post("/api/categories", response_model=Categoria, status_code=201)
async def crear_categoria(
    request: Request, peticion: CrearCategoria
) -> Categoria:
    """Crea una nueva categoría en el catálogo dinámico."""
    try:
        return _categoria_manager(request).crear(
            nombre=peticion.nombre,
            id=peticion.id,
            color=peticion.color,
            icono=peticion.icono,
            ubicacion_default=peticion.ubicacion_default,
            orden=peticion.orden,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/categories/{categoria_id}", response_model=Categoria)
async def actualizar_categoria(
    request: Request,
    categoria_id: str,
    peticion: ActualizarCategoria,
) -> Categoria:
    """Actualiza los campos editables de una categoría."""
    manager = _categoria_manager(request)
    try:
        return manager.actualizar(
            categoria_id, **peticion.model_dump(exclude_unset=True)
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"Categoría no encontrada: {categoria_id}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/categories/{categoria_id}", response_model=RespuestaBorrarCategoria)
async def borrar_categoria(
    request: Request,
    categoria_id: str,
    reemplazar_por: Optional[str] = None,
) -> RespuestaBorrarCategoria:
    """Elimina una categoría. Si tiene ítems asociados devuelve 409.

    Si se pasa ``reemplazar_por``, todos los ítems de la categoría se
    reasignan a esa categoría antes de borrarla.
    """
    manager = _categoria_manager(request)
    if not manager.existe(categoria_id):
        raise HTTPException(
            status_code=404, detail=f"Categoría no encontrada: {categoria_id}"
        )

    vault = _vault(request)
    items = await vault.list_items()
    afectados = [i.id for i in items if i.categoria == categoria_id]

    if afectados and reemplazar_por is None:
        raise HTTPException(
            status_code=409,
            detail={
                "categoria": categoria_id,
                "items_afectados": afectados,
            },
        )

    if reemplazar_por is not None:
        if not manager.existe(reemplazar_por):
            raise HTTPException(
                status_code=400,
                detail=f"Categoría de reemplazo no válida: {reemplazar_por}",
            )
        for item_id in afectados:
            await vault.move_item(item_id, nueva_categoria=reemplazar_por)

    manager.borrar(categoria_id)
    return RespuestaBorrarCategoria(
        eliminada=True, items_afectados=afectados
    )


# --- CRUD de inventario (crear/editar/borrar/mover) ---------------------------


class ActualizarItem(BaseModel):
    """Cuerpo de PUT /api/inventory/{item_id}."""

    nombre: Optional[str] = None
    categoria: Optional[str] = None
    ubicacion: Optional[str] = None
    stock_minimo: Optional[float] = None
    unidad: Optional[str] = None
    precio_unitario_estimado: Optional[float] = None
    dias_promedio_consumo: Optional[float] = None
    auto_lista_compra: Optional[bool] = None
    tags: Optional[list[str]] = None
    ean_barcode: Optional[str] = None


class MoverItem(BaseModel):
    """Cuerpo de POST /api/inventory/{item_id}/move."""

    categoria: Optional[str] = None
    ubicacion: Optional[str] = None


@app.post("/api/inventory", response_model=Consumible, status_code=201)
async def crear_item(request: Request, item: Consumible) -> Consumible:
    """Crea un nuevo ítem de inventario en ``inventario/<ubicacion>/<id>.md``."""
    try:
        return await _vault(request).create_item(item)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/inventory/{item_id}", response_model=Consumible)
async def actualizar_item(
    request: Request, item_id: str, peticion: ActualizarItem
) -> Consumible:
    """Actualiza los campos editables de un ítem preservando el cuerpo.

    Si la petición cambia ``ubicacion`` y/o ``categoria``, se delega en
    ``move_item`` (con validación de categoría contra el catálogo dinámico);
    el resto de campos editables se aplican con ``update_item``.
    """
    vault = _vault(request)
    cambios = {
        k: v
        for k, v in peticion.model_dump(exclude_unset=True).items()
        if v is not None
    }
    ubicacion_nueva = cambios.pop("ubicacion", None)
    categoria_nueva = cambios.pop("categoria", None)

    try:
        if ubicacion_nueva is not None or categoria_nueva is not None:
            await vault.move_item(
                item_id,
                nueva_categoria=categoria_nueva,
                nueva_ubicacion=ubicacion_nueva,
            )
        if cambios:
            return await vault.update_item(item_id, cambios)
        item = await vault.get_item(item_id)
        if item is None:
            raise KeyError(f"Ítem no encontrado: {item_id}")
        return item
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/inventory/{item_id}", status_code=204)
async def borrar_item(request: Request, item_id: str) -> None:
    """Elimina el archivo .md de un ítem de inventario."""
    borrado = await _vault(request).delete_item(item_id)
    if not borrado:
        raise HTTPException(
            status_code=404, detail=f"Ítem no encontrado: {item_id}"
        )


@app.post("/api/inventory/{item_id}/move", response_model=Consumible)
async def mover_item(
    request: Request, item_id: str, peticion: MoverItem
) -> Consumible:
    """Mueve un ítem a otra ubicación y/o cambia su categoría."""
    try:
        return await _vault(request).move_item(
            item_id,
            nueva_categoria=peticion.categoria,
            nueva_ubicacion=peticion.ubicacion,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# --- CRUD de recetas ----------------------------------------------------------


class ActualizarReceta(BaseModel):
    """Cuerpo de PUT /api/recipes/{id}."""

    titulo: Optional[str] = None
    categoria: Optional[str] = None
    tiempo_minutos: Optional[int] = None
    raciones: Optional[int] = None
    calorias_racion: Optional[int] = None
    ingredientes: Optional[list[Ingrediente]] = None
    tags: Optional[list[str]] = None


class CocinarReceta(BaseModel):
    """Cuerpo de POST /api/recipes/{id}/cook."""

    raciones: Optional[int] = None


@app.post("/api/recipes", response_model=Receta, status_code=201)
async def crear_receta(request: Request, receta: Receta) -> Receta:
    """Crea una nueva receta en ``recetas/<id>.md``."""
    try:
        return await _vault(request).create_receta(receta)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/recipes/possible", response_model=list[RecetaPosible])
async def recetas_posibles(request: Request) -> list[RecetaPosible]:
    """Recetas ordenadas por los ingredientes disponibles en inventario."""
    return await _planner(request).possible_recipes()


@app.get("/api/recipes/{id}", response_model=Receta)
async def obtener_receta(request: Request, id: str) -> Receta:
    """Devuelve una receta por su id."""
    receta = await _vault(request).get_receta(id)
    if receta is None:
        raise HTTPException(
            status_code=404, detail=f"Receta no encontrada: {id}"
        )
    return receta


@app.put("/api/recipes/{id}", response_model=Receta)
async def actualizar_receta(
    request: Request, id: str, peticion: ActualizarReceta
) -> Receta:
    """Actualiza los campos editables de una receta."""
    cambios = peticion.model_dump(exclude_unset=True)
    try:
        return await _vault(request).update_receta(id, cambios)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/recipes/{id}", status_code=204)
async def borrar_receta(request: Request, id: str) -> None:
    """Elimina el archivo .md de una receta."""
    borrada = await _vault(request).delete_receta(id)
    if not borrada:
        raise HTTPException(
            status_code=404, detail=f"Receta no encontrada: {id}"
        )


@app.get("/api/recipes/possible", response_model=list[RecetaPosible])
async def recetas_posibles(request: Request) -> list[RecetaPosible]:
    """Recetas ordenadas por los ingredientes disponibles en inventario."""
    return await _planner(request).possible_recipes()


@app.post("/api/recipes/{id}/cook", response_model=ResultadoCocinarReceta)
async def cocinar_receta(
    request: Request, id: str, peticion: CocinarReceta
) -> ResultadoCocinarReceta:
    """Consume del inventario los ingredientes de una receta.

    Es transaccional: si falta stock para algún ingrediente no se consume
    nada y se devuelve 409 con el listado de faltantes.
    """
    try:
        return await _planner(request).cook_recipe(id, raciones=peticion.raciones)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InsufficientStockError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "mensaje": "Stock insuficiente para cocinar la receta",
                "faltantes": [
                    f.model_dump() for f in exc.faltantes
                ],
            },
        ) from exc
