"""Tests del observador del vault, WebSocketManager y router /ws (Fase 4)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from watchdog.events import DirCreatedEvent, FileModifiedEvent

from backend.routers.ws import router as ws_router
from backend.watcher import (
    EventoVault,
    TipoEvento,
    VaultWatcher,
    WebSocketManager,
    _HandlerVault,
    clasificar_ruta,
)

# --- Clasificación de rutas ---------------------------------------------------


@pytest.mark.parametrize(
    "ruta, esperado",
    [
        ("inventario/nevera/yogur.md", TipoEvento.INVENTORY_UPDATED),
        ("inventario/limpieza/lejia.md", TipoEvento.INVENTORY_UPDATED),
        ("tareas/limpiar_bano.md", TipoEvento.TASK_CHANGED),
        ("planificador/2026-W34.md", TipoEvento.MEAL_PLAN_SYNCED),
        ("listas/compra.md", TipoEvento.SHOPPING_LIST_UPDATED),
        ("recetas/paella.md", TipoEvento.GENERIC_UPDATE),
        ("gastos/2026-08.md", TipoEvento.GENERIC_UPDATE),
        ("sueltos.md", TipoEvento.GENERIC_UPDATE),
    ],
)
def test_clasificar_ruta(ruta: str, esperado: TipoEvento) -> None:
    """Cada subdirectorio del vault se mapea a su tipo de evento."""
    assert clasificar_ruta(ruta) is esperado


def test_evento_vault_a_json() -> None:
    """El evento se serializa con el tipo como string (JSON-compatible)."""
    evento = EventoVault(
        tipo=TipoEvento.TASK_CHANGED, ruta="tareas/x.md", accion="modified"
    )
    assert evento.a_json() == {
        "tipo": "TASK_CHANGED",
        "ruta": "tareas/x.md",
        "accion": "modified",
    }


# --- Handler watchdog -> asyncio ----------------------------------------------


async def test_handler_encola_evento_clasificado(vault_path: Path) -> None:
    """El handler convierte el callback de hilo en EventoVault en la cola."""
    cola: asyncio.Queue[EventoVault] = asyncio.Queue()
    handler = _HandlerVault(asyncio.get_running_loop(), cola, vault_path)
    ruta = vault_path / "inventario" / "nevera" / "yogur.md"
    handler.on_any_event(FileModifiedEvent(str(ruta)))
    evento = await asyncio.wait_for(cola.get(), timeout=1)
    assert evento.tipo is TipoEvento.INVENTORY_UPDATED
    assert evento.ruta == "inventario/nevera/yogur.md"
    assert evento.accion == "modified"


async def test_handler_ignora_directorios_y_tmp(vault_path: Path) -> None:
    """No se encolan eventos de directorio ni temporales de escritura."""
    cola: asyncio.Queue[EventoVault] = asyncio.Queue()
    handler = _HandlerVault(asyncio.get_running_loop(), cola, vault_path)
    handler.on_any_event(DirCreatedEvent(str(vault_path / "tareas")))
    handler.on_any_event(
        FileModifiedEvent(str(vault_path / "tareas" / "x.md.tmp"))
    )
    await asyncio.sleep(0.05)  # margen para que call_soon_threadsafe corriera
    assert cola.empty()


# --- VaultWatcher con observer real sobre vault temporal ----------------------


async def test_watcher_publica_eventos_a_suscriptores(vault_path: Path) -> None:
    """Un archivo creado en tareas/ genera un TASK_CHANGED al suscriptor."""
    watcher = VaultWatcher(vault_path)
    recibidos: list[EventoVault] = []
    listo = asyncio.Event()

    async def suscriptor(evento: EventoVault) -> None:
        recibidos.append(evento)
        listo.set()

    watcher.suscribir(suscriptor)
    await watcher.start()
    try:
        await asyncio.sleep(0.1)  # margen para que el observer arranque
        (vault_path / "tareas" / "nueva.md").write_text(
            "---\nid: t\n---\n", encoding="utf-8"
        )
        await asyncio.wait_for(listo.wait(), timeout=5)
    finally:
        await watcher.stop()
    assert any(
        e.tipo is TipoEvento.TASK_CHANGED and e.ruta == "tareas/nueva.md"
        for e in recibidos
    )


async def test_watcher_stop_sin_start() -> None:
    """Detener un watcher no arrancado no falla."""
    watcher = VaultWatcher(Path("/tmp/vault_inexistente"))
    await watcher.stop()


# --- WebSocketManager con clientes fake ---------------------------------------


class FakeWebSocket:
    """Fake de WebSocket: registra accept y los JSON enviados."""

    def __init__(self, fallar: bool = False) -> None:
        self.aceptado = False
        self.enviados: list[dict] = []
        self._fallar = fallar

    async def accept(self) -> None:
        self.aceptado = True

    async def send_json(self, mensaje: dict) -> None:
        if self._fallar:
            raise ConnectionError("socket roto")
        self.enviados.append(mensaje)


async def test_ws_manager_connect_disconnect() -> None:
    """connect acepta y registra; disconnect lo elimina e idempotente."""
    manager = WebSocketManager()
    ws = FakeWebSocket()
    await manager.connect(ws)
    assert ws.aceptado
    assert manager.num_conexiones == 1
    manager.disconnect(ws)
    manager.disconnect(ws)  # idempotente
    assert manager.num_conexiones == 0


async def test_ws_manager_broadcast_a_todos() -> None:
    """broadcast envía el JSON a todas las conexiones activas."""
    manager = WebSocketManager()
    ws1, ws2 = FakeWebSocket(), FakeWebSocket()
    await manager.connect(ws1)
    await manager.connect(ws2)
    mensaje = {"tipo": "INVENTORY_UPDATED", "ruta": "inventario/a.md"}
    await manager.broadcast(mensaje)
    assert ws1.enviados == [mensaje]
    assert ws2.enviados == [mensaje]


async def test_ws_manager_broadcast_elimina_conexiones_rotas() -> None:
    """Una conexión que falla al enviar se desregistra sin romper el resto."""
    manager = WebSocketManager()
    roto, sano = FakeWebSocket(fallar=True), FakeWebSocket()
    await manager.connect(roto)
    await manager.connect(sano)
    await manager.broadcast({"tipo": "GENERIC_UPDATE"})
    assert manager.num_conexiones == 1
    assert sano.enviados == [{"tipo": "GENERIC_UPDATE"}]


# --- Router /ws con TestClient -------------------------------------------------


def test_router_ws_registra_cliente_en_manager() -> None:
    """El endpoint /ws registra la conexión en app.state.ws_manager."""
    app = FastAPI()
    manager = WebSocketManager()
    app.state.ws_manager = manager
    app.include_router(ws_router)

    cliente = TestClient(app)
    assert manager.num_conexiones == 0
    with cliente.websocket_connect("/ws"):
        assert manager.num_conexiones == 1
    assert manager.num_conexiones == 0


def test_router_ws_recibe_evento_broadcast() -> None:
    """Un broadcast del manager llega al cliente conectado a /ws."""
    app = FastAPI()
    manager = WebSocketManager()
    app.state.ws_manager = manager
    app.include_router(ws_router)

    with TestClient(app) as cliente:
        with cliente.websocket_connect("/ws") as ws:
            # broadcast desde el hilo del test vía el portal del TestClient
            cliente.portal.call(manager.broadcast, {"tipo": "TASK_CHANGED"})
            assert ws.receive_json() == {"tipo": "TASK_CHANGED"}
