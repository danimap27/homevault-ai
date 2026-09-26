"""Sincronizador bidireccional entre HomeVault AI y Google Workspace.

Toda la lógica de negocio vive en la clase GoogleSync, que trabaja contra
clientes de API INYECTADOS con una interfaz mínima (list/insert/patch de
tareas e insert de eventos). Esto permite testear con fakes sin credenciales
reales. La construcción de credenciales OAuth2 y de los clientes reales de
googleapiclient está encapsulada en la factoría build_google_sync().
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Protocol

from dateutil.relativedelta import relativedelta

from backend.config import Settings
from backend.models import Frecuencia, HistorialCompletado, Tarea
from backend.vault_manager import VaultManager, ahora_utc

logger = logging.getLogger(__name__)

# Scopes OAuth2: Google Tasks + Google Calendar
SCOPES = [
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/calendar",
]

# Deltas de reprogramación por frecuencia
_DELTAS_FRECUENCIA: dict[str, timedelta | relativedelta] = {
    "diaria": timedelta(days=1),
    "semanal": timedelta(weeks=1),
    "quincenal": timedelta(weeks=2),
    "mensual": relativedelta(months=+1),
    "cada_3_meses": relativedelta(months=+3),
    "cada_6_meses": relativedelta(months=+6),
    "anual": relativedelta(years=+1),
}


class ClienteTasks(Protocol):
    """Interfaz mínima del cliente de Google Tasks (fácil de falsear)."""

    def list_tasks(self, tasklist: str) -> list[dict]:
        """Devuelve las tareas remotas de la lista como dicts crudos."""
        ...

    def insert_task(self, tasklist: str, body: dict) -> dict:
        """Crea una tarea remota y devuelve el dict con su id."""
        ...

    def patch_task(self, tasklist: str, task_id: str, body: dict) -> dict:
        """Actualiza parcialmente una tarea remota."""
        ...


class ClienteCalendar(Protocol):
    """Interfaz mínima del cliente de Google Calendar."""

    def insert_event(self, calendar_id: str, body: dict) -> dict:
        """Crea un evento y devuelve el dict con su id."""
        ...


class GoogleApiAdapter:
    """Adaptador de los recursos de googleapiclient a la interfaz mínima.

    Envuelve los recursos tasks().* y events().* del cliente oficial en
    métodos simples que devuelven dicts, ocultando el encadenamiento
    .execute() propio de googleapiclient.
    """

    def __init__(self, servicio_tasks, servicio_calendar) -> None:
        self._tasks = servicio_tasks
        self._calendar = servicio_calendar

    def list_tasks(self, tasklist: str) -> list[dict]:
        respuesta = (
            self._tasks.tasks()
            .list(tasklist=tasklist, showCompleted=True, showHidden=True)
            .execute()
        )
        return respuesta.get("items", [])

    def insert_task(self, tasklist: str, body: dict) -> dict:
        return self._tasks.tasks().insert(tasklist=tasklist, body=body).execute()

    def patch_task(self, tasklist: str, task_id: str, body: dict) -> dict:
        return (
            self._tasks.tasks()
            .patch(tasklist=tasklist, task=task_id, body=body)
            .execute()
        )

    def insert_event(self, calendar_id: str, body: dict) -> dict:
        return (
            self._calendar.events()
            .insert(calendarId=calendar_id, body=body)
            .execute()
        )


def build_google_sync(vault: VaultManager, settings: Settings) -> "GoogleSync":
    """Factoría: construye un GoogleSync con clientes reales de Google.

    Ejecuta el flujo OAuth2 installed-app: lee credentials.json de
    settings.google_credentials_dir, reutiliza token.json si es válido y lo
    refresca o reautoriza en caso contrario.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    directorio: Path = settings.google_credentials_dir
    ruta_token = directorio / "token.json"
    ruta_credenciales = directorio / "credentials.json"

    creds: Optional[Credentials] = None
    if ruta_token.exists():
        creds = Credentials.from_authorized_user_file(str(ruta_token), SCOPES)
    if creds is None or not creds.valid:
        if creds is not None and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flujo = InstalledAppFlow.from_client_secrets_file(
                str(ruta_credenciales), SCOPES
            )
            creds = flujo.run_local_server(port=0)
        directorio.mkdir(parents=True, exist_ok=True)
        ruta_token.write_text(creds.to_json(), encoding="utf-8")

    servicio_tasks = build("tasks", "v1", credentials=creds)
    servicio_calendar = build("calendar", "v3", credentials=creds)
    adaptador = GoogleApiAdapter(servicio_tasks, servicio_calendar)
    return GoogleSync(
        vault=vault,
        tasks_client=adaptador,
        calendar_client=adaptador,
        tasks_list_id=settings.google_tasks_list_id,
        calendar_id=settings.google_calendar_id,
    )


def calcular_siguiente_fecha(base: date, frecuencia: Frecuencia) -> Optional[date]:
    """Suma la frecuencia a la fecha base. None si la frecuencia es 'unica'."""
    delta = _DELTAS_FRECUENCIA.get(frecuencia)
    if delta is None:
        return None
    return base + delta


class GoogleSync:
    """Sincronizador bidireccional vault <-> Google Tasks/Calendar.

    Si los clientes son None (p. ej. sin credenciales), toda la lógica local
    del vault sigue funcionando y las operaciones remotas se omiten.
    """

    def __init__(
        self,
        vault: VaultManager,
        tasks_client: Optional[ClienteTasks] = None,
        calendar_client: Optional[ClienteCalendar] = None,
        tasks_list_id: str = "@default",
        calendar_id: str = "primary",
    ) -> None:
        self.vault = vault
        self.tasks_client = tasks_client
        self.calendar_client = calendar_client
        self.tasks_list_id = tasks_list_id
        self.calendar_id = calendar_id
        # Ids de Google ya procesados por el polling (evita doble disparo)
        self._procesados_poll: set[str] = set()

    # --- Helpers de formato Google ---------------------------------------------

    @staticmethod
    def _body_tarea_google(tarea: Tarea) -> dict:
        """Cuerpo de una tarea de Google Tasks a partir de la Tarea local."""
        body: dict = {
            "title": tarea.titulo,
            "notes": f"homevault:{tarea.id}",
        }
        if tarea.fecha_programada is not None:
            # Google Tasks exige RFC3339; usamos medianoche UTC del día
            body["due"] = (
                f"{tarea.fecha_programada.isoformat()}T00:00:00.000Z"
            )
        return body

    @staticmethod
    def _body_evento_calendar(tarea: Tarea) -> dict:
        """Cuerpo de un evento de día completo de Google Calendar."""
        assert tarea.fecha_programada is not None
        return {
            "summary": tarea.titulo,
            "description": f"Tarea HomeVault: {tarea.id}",
            "start": {"date": tarea.fecha_programada.isoformat()},
            "end": {"date": tarea.fecha_programada.isoformat()},
        }

    # --- Operaciones remotas (omitibles sin clientes) ---------------------------

    async def _insertar_tarea_remota(self, tarea: Tarea) -> Optional[str]:
        """Crea la tarea en Google Tasks y devuelve su id remoto."""
        if self.tasks_client is None:
            return None
        respuesta = await asyncio.to_thread(
            self.tasks_client.insert_task,
            self.tasks_list_id,
            self._body_tarea_google(tarea),
        )
        return respuesta.get("id")

    async def _insertar_evento_remoto(self, tarea: Tarea) -> Optional[str]:
        """Crea el evento en Google Calendar y devuelve su id remoto."""
        if self.calendar_client is None or tarea.fecha_programada is None:
            return None
        respuesta = await asyncio.to_thread(
            self.calendar_client.insert_event,
            self.calendar_id,
            self._body_evento_calendar(tarea),
        )
        return respuesta.get("id")

    async def _marcar_completada_remota(self, google_task_id: str) -> None:
        """Marca la tarea como completada en Google Tasks."""
        if self.tasks_client is None:
            return
        await asyncio.to_thread(
            self.tasks_client.patch_task,
            self.tasks_list_id,
            google_task_id,
            {"status": "completed"},
        )

    # --- API pública -------------------------------------------------------------

    async def create_task_in_google(self, tarea: Tarea) -> Tarea:
        """Crea la tarea en Google Tasks (y Calendar si tiene fecha).

        Persiste google_task_id y google_calendar_event_id en el .md local.
        """
        google_task_id = await self._insertar_tarea_remota(tarea)
        if google_task_id:
            tarea.google_task_id = google_task_id
        evento_id = await self._insertar_evento_remoto(tarea)
        if evento_id:
            tarea.google_calendar_event_id = evento_id
        await self.vault.save_task(tarea)
        return tarea

    async def complete_task(
        self, task_id_local: str, completed_by: Optional[str] = None
    ) -> Tarea:
        """Completa una tarea: historial, rotación, reprogramación y sync.

        Regla de estado estricto: la tarea solo se completa a través de este
        método (UI/MCP) o del polling que detecta status=completed remoto.
        """
        tarea = await self.vault.get_task(task_id_local)
        if tarea is None:
            raise KeyError(f"Tarea no encontrada: {task_id_local}")

        ahora = ahora_utc()
        hoy = ahora.date()

        # 1. Historial de completados
        tarea.historial_completados.append(
            HistorialCompletado(fecha=hoy, usuario=completed_by)
        )

        # 2. Rotación de convivientes
        if tarea.rotacion_convivientes:
            tarea.indice_rotacion_actual = (
                tarea.indice_rotacion_actual + 1
            ) % len(tarea.rotacion_convivientes)
            tarea.asignado_a = tarea.rotacion_convivientes[
                tarea.indice_rotacion_actual
            ]

        # 3. Reprogramación según frecuencia
        base = tarea.fecha_programada or hoy
        siguiente = calcular_siguiente_fecha(base, tarea.frecuencia)
        reprograma = siguiente is not None
        if reprograma:
            tarea.fecha_programada = siguiente
            tarea.estado = "pendiente"
        else:
            tarea.estado = "completada"

        # 4. Marcar completada en Google y crear la siguiente ocurrencia
        if tarea.google_task_id:
            self._procesados_poll.add(tarea.google_task_id)
            await self._marcar_completada_remota(tarea.google_task_id)
        if reprograma and self.tasks_client is not None:
            nuevo_id = await self._insertar_tarea_remota(tarea)
            if nuevo_id:
                tarea.google_task_id = nuevo_id
            evento_id = await self._insertar_evento_remoto(tarea)
            if evento_id:
                tarea.google_calendar_event_id = evento_id

        # 5. Marca temporal y persistencia
        tarea.ultima_realizacion = ahora
        await self.vault.save_task(tarea)
        return tarea

    async def check_consumables_before_task(self, task_id_local: str) -> Tarea:
        """Verifica stock de los consumibles con verificar_stock_previo.

        Si falta stock de alguno, lo añade a listas/compra.md (reutilizando
        el trigger del VaultManager) y marca bloqueada_por_stock=true. Si hay
        stock suficiente de todos, la deja en false. Persiste el .md.
        """
        tarea = await self.vault.get_task(task_id_local)
        if tarea is None:
            raise KeyError(f"Tarea no encontrada: {task_id_local}")

        bloqueada = False
        for requerido in tarea.consumibles_requeridos:
            if not requerido.verificar_stock_previo:
                continue
            item = await self.vault.get_item(requerido.item_id)
            if item is None:
                logger.warning(
                    "Consumible requerido no encontrado: %s",
                    requerido.item_id,
                )
                bloqueada = True
                continue
            if item.stock_actual < requerido.cantidad:
                await self.vault._add_to_shopping_list(item)
                bloqueada = True

        if tarea.bloqueada_por_stock != bloqueada:
            tarea.bloqueada_por_stock = bloqueada
            await self.vault.save_task(tarea)
        return tarea

    async def poll_google_tasks(self) -> list[str]:
        """Procesa las tareas completadas en remoto pendientes en local.

        Para cada tarea remota con status=completed cuyo google_task_id exista
        en el vault con estado=pendiente, ejecuta el mismo flujo de
        complete_task. Devuelve los ids locales procesados.

        Diseñado para ser llamado periódicamente (cron/background task); no
        implementa el bucle infinito.
        """
        if self.tasks_client is None:
            return []
        remotas = await asyncio.to_thread(
            self.tasks_client.list_tasks, self.tasks_list_id
        )
        procesadas: list[str] = []
        for remota in remotas:
            if remota.get("status") != "completed":
                continue
            google_id = remota.get("id", "")
            if not google_id or google_id in self._procesados_poll:
                continue
            tarea = await self.vault.get_task_by_google_id(google_id)
            if tarea is None or tarea.estado != "pendiente":
                continue
            await self.complete_task(tarea.id, completed_by=tarea.asignado_a)
            procesadas.append(tarea.id)
        return procesadas
