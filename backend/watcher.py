"""Observador del vault con watchdog y gestor de WebSockets (Fase 4).

Convierte los callbacks síncronos de watchdog (hilo propio) en eventos
asyncio, clasificándolos por la ruta del archivo modificado dentro del
vault. WebSocketManager gestiona las conexiones de clientes para emitirles
esos eventos en JSON.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class TipoEvento(str, Enum):
    """Tipos de evento del vault que se emiten a los clientes WebSocket."""

    INVENTORY_UPDATED = "INVENTORY_UPDATED"
    TASK_CHANGED = "TASK_CHANGED"
    MEAL_PLAN_SYNCED = "MEAL_PLAN_SYNCED"
    SHOPPING_LIST_UPDATED = "SHOPPING_LIST_UPDATED"
    GENERIC_UPDATE = "GENERIC_UPDATE"


# Primer componente de la ruta relativa al vault -> tipo de evento
_MAPA_DIRECTORIOS = {
    "inventario": TipoEvento.INVENTORY_UPDATED,
    "tareas": TipoEvento.TASK_CHANGED,
    "planificador": TipoEvento.MEAL_PLAN_SYNCED,
    "listas": TipoEvento.SHOPPING_LIST_UPDATED,
}


@dataclass
class EventoVault:
    """Evento de cambio en un archivo del vault, listo para serializar."""

    tipo: TipoEvento
    ruta: str  # ruta relativa al vault, con separadores POSIX
    accion: str  # created | modified | deleted | moved

    def a_json(self) -> dict:
        """Serializa el evento a un dict JSON-compatible."""
        datos = asdict(self)
        datos["tipo"] = self.tipo.value
        return datos


def clasificar_ruta(ruta_relativa: str) -> TipoEvento:
    """Clasifica una ruta relativa al vault en su tipo de evento."""
    partes = Path(ruta_relativa).parts
    if partes:
        tipo = _MAPA_DIRECTORIOS.get(partes[0])
        if tipo is not None:
            return tipo
    return TipoEvento.GENERIC_UPDATE


class _HandlerVault(FileSystemEventHandler):
    """Handler de watchdog que puenteCallbacks de hilo a cola asyncio.

    watchdog invoca los callbacks desde su propio hilo; aquí solo se
    encolan los eventos con loop.call_soon_threadsafe, sin lógica async.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        cola: "asyncio.Queue[EventoVault]",
        vault_path: Path,
    ) -> None:
        super().__init__()
        self._loop = loop
        self._cola = cola
        self._vault_path = vault_path

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Traduce un evento de watchdog a EventoVault y lo encola."""
        if event.is_directory:
            return
        ruta = Path(event.src_path)
        # Se ignoran los temporales de la escritura atómica del VaultManager
        if ruta.suffix == ".tmp":
            return
        try:
            relativa = ruta.relative_to(self._vault_path).as_posix()
        except ValueError:
            return  # archivo fuera del vault (no debería ocurrir)
        evento = EventoVault(
            tipo=clasificar_ruta(relativa),
            ruta=relativa,
            accion=event.event_type,
        )
        self._loop.call_soon_threadsafe(self._cola.put_nowait, evento)


CallbackEvento = Callable[[EventoVault], Awaitable[None]]


class VaultWatcher:
    """Observador async del vault: publica EventoVault a sus suscriptores.

    El Observer de watchdog es inyectable para tests; si no se pasa, se
    crea uno real en start().
    """

    def __init__(
        self,
        vault_path: Path | str,
        observer: Optional[Observer] = None,
    ) -> None:
        self.vault_path = Path(vault_path)
        self._observer_inyectado = observer
        self._observer: Optional[Observer] = None
        self._cola: "asyncio.Queue[EventoVault]" = asyncio.Queue()
        self._suscriptores: list[CallbackEvento] = []
        self._tarea_consumidora: Optional[asyncio.Task] = None

    def suscribir(self, callback: CallbackEvento) -> None:
        """Registra un callback async que recibirá cada EventoVault."""
        self._suscriptores.append(callback)

    async def start(self) -> None:
        """Arranca el observer de watchdog y la tarea consumidora."""
        self._observer = self._observer_inyectado or Observer()
        handler = _HandlerVault(
            asyncio.get_running_loop(), self._cola, self.vault_path
        )
        self._observer.schedule(handler, str(self.vault_path), recursive=True)
        self._observer.start()
        self._tarea_consumidora = asyncio.create_task(self._bucle_eventos())
        logger.info("VaultWatcher observando %s", self.vault_path)

    async def stop(self) -> None:
        """Detiene el observer y la tarea consumidora."""
        if self._tarea_consumidora is not None:
            self._tarea_consumidora.cancel()
            try:
                await self._tarea_consumidora
            except asyncio.CancelledError:
                pass
            self._tarea_consumidora = None
        if self._observer is not None:
            # stop/join son bloqueantes: se ejecutan fuera del bucle
            await asyncio.to_thread(self._observer.stop)
            await asyncio.to_thread(self._observer.join)
            self._observer = None
        logger.info("VaultWatcher detenido")

    async def _bucle_eventos(self) -> None:
        """Consume la cola y publica cada evento a los suscriptores."""
        while True:
            evento = await self._cola.get()
            await self._publicar(evento)

    async def _publicar(self, evento: EventoVault) -> None:
        """Notifica un evento a todos los suscriptores tolerando fallos."""
        for callback in self._suscriptores:
            try:
                await callback(evento)
            except Exception:
                logger.exception(
                    "Error en suscriptor del VaultWatcher (%s)", evento.ruta
                )


class WebSocketManager:
    """Gestor de conexiones WebSocket con difusión de mensajes JSON.

    Las conexiones solo necesitan accept() y send_json(); en tests se
    inyectan fakes con esa interfaz mínima.
    """

    def __init__(self) -> None:
        self._conexiones: set = set()

    @property
    def num_conexiones(self) -> int:
        """Número de clientes conectados actualmente."""
        return len(self._conexiones)

    async def connect(self, websocket) -> None:
        """Acepta y registra una nueva conexión WebSocket."""
        await websocket.accept()
        self._conexiones.add(websocket)

    def disconnect(self, websocket) -> None:
        """Elimina una conexión del registro (idempotente)."""
        self._conexiones.discard(websocket)

    async def broadcast(self, mensaje: dict) -> None:
        """Envía un mensaje JSON a todos los clientes conectados.

        Las conexiones que fallan al enviar se eliminan del registro.
        """
        rotas: list = []
        for websocket in self._conexiones:
            try:
                await websocket.send_json(mensaje)
            except Exception:
                logger.warning("Conexión WebSocket rota; se desregistra")
                rotas.append(websocket)
        for websocket in rotas:
            self.disconnect(websocket)
