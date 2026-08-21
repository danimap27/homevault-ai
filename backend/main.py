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
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.ai_vision_parser import (
    ErrorParseoTicket,
    GastoMes,
    ReceiptParser,
    ResultadoRegistroCompra,
    build_llm_client,
)
from backend.config import get_settings
from backend.git_sync import GitSync
from backend.google_sync import GoogleSync, build_google_sync
from backend.models import (
    Consumible,
    EntradaListaCompra,
    ItemCaducidad,
    ItemHuerfano,
    PlanSemanal,
    Receta,
    ResultadoCompra,
    ResultadoConsumo,
    Tarea,
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


class PeticionCompletarTarea(BaseModel):
    """Cuerpo de POST /api/tasks/{task_id}/complete."""

    completed_by: Optional[str] = None


class PeticionTicketTexto(BaseModel):
    """Cuerpo JSON de POST /api/ingest/receipt (ticket en texto)."""

    texto: str
    comercio: Optional[str] = None
    total: Optional[float] = Field(default=None, ge=0)


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


def _sync(request: Request) -> GoogleSync:
    """Recupera el GoogleSync del estado de la app."""
    return request.app.state.google_sync


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
    )


@app.get("/api/shopping-list", response_model=list[EntradaListaCompra])
async def lista_compra(request: Request) -> list[EntradaListaCompra]:
    """Contenido parseado de listas/compra.md."""
    return await _vault(request).get_shopping_list()


# --- Ingesta de tickets con IA (Fase 3) -------------------------------------------


@app.post("/api/ingest/receipt", response_model=ResultadoRegistroCompra)
async def ingerir_ticket(request: Request) -> ResultadoRegistroCompra:
    """Ingesta un ticket y lo registra en cascada (inventario + gastos).

    Admite dos formatos: imagen del ticket como multipart/form-data (campo
    "imagen") o texto en lenguaje natural como JSON ({texto, comercio?,
    total?}).
    """
    parser: Optional[ReceiptParser] = getattr(
        request.app.state, "receipt_parser", None
    )
    if parser is None:
        raise HTTPException(
            status_code=503,
            detail="Proveedor de IA no configurado (AI_PROVIDER)",
        )
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
            ticket = await parser.parse_ticket_from_image(
                await archivo.read(),
                mime_type=archivo.content_type or "image/jpeg",
            )
        else:
            cuerpo = PeticionTicketTexto.model_validate(await request.json())
            ticket = await parser.parse_ticket_from_text(
                cuerpo.texto, comercio=cuerpo.comercio, total=cuerpo.total
            )
    except ErrorParseoTicket as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await parser.register_purchase(ticket)


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
