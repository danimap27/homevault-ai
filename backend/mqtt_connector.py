"""Conector MQTT + Home Assistant de HomeVault AI (Fase 4a).

Funcionalidad:
1. Suscripción a ``home/sensors/+/+/weight``: al recibir un peso (en gramos)
   busca el consumible cuyo ``mqtt_sensor_topic`` coincida con el tópico y
   actualiza su ``stock_actual`` en el .md. Convierte gramos a la unidad del
   ítem (gramos -> directo, kg -> /1000); si no hay conversión posible, guarda
   el peso crudo como nota en el cuerpo del Markdown.
2. Publicación de MQTT Discovery (``homeassistant/sensor/homevault_<id>/config``)
   para consumibles con stock_actual <= stock_minimo y para tareas pendientes,
   de modo que aparezcan como sensores en Home Assistant.
3. Avisos matutinos: publica en ``home/tts/say`` los alimentos que caducan en
   menos de 48 horas y las tareas del día agrupadas por conviviente.

El cliente MQTT es INYECTABLE (protocolo ClienteMQTT): los tests usan un broker
fake sin conexión real. La factoría build_mqtt_connector() construye el
adaptador real sobre aiomqtt con import perezoso.

Nota: la actualización de stock usa helpers internos del VaultManager
(_find_item_path/_get_lock/_read_doc/_write_doc) porque no existe aún un método
público de "lectura absoluta de sensor". Si el integrador añade
``VaultManager.update_stock_from_sensor``, este módulo debería migrar a él.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional, Protocol

from backend.config import Settings
from backend.models import Consumible, Tarea
from backend.vault_manager import VaultManager, ahora_utc

logger = logging.getLogger(__name__)

# Tópico de suscripción a básculas/sensores de peso (payload en gramos)
TOPICO_PESOS = "home/sensors/+/+/weight"
# Tópico TTS para los avisos hablados
TOPICO_TTS = "home/tts/say"
# Prefijo de MQTT Discovery de Home Assistant
PREFIJO_DISCOVERY = "homeassistant"

# Marca de la nota de peso crudo en el cuerpo del .md
_MARCA_NOTA_SENSOR = "> Sensor MQTT:"


@dataclass
class MensajeMQTT:
    """Mensaje MQTT normalizado (independiente de la librería cliente)."""

    topic: str
    payload: bytes


class ClienteMQTT(Protocol):
    """Interfaz mínima del cliente MQTT (fácil de falsear en tests)."""

    async def connect(self) -> None:
        """Establece la conexión con el broker (no-op en fakes)."""
        ...

    async def disconnect(self) -> None:
        """Cierra la conexión con el broker (no-op en fakes)."""
        ...

    async def subscribe(self, topic: str) -> None:
        """Suscribe un tópico (admite comodines MQTT)."""
        ...

    async def publish(
        self, topic: str, payload: str, retain: bool = False
    ) -> None:
        """Publica un payload de texto en un tópico."""
        ...

    async def messages(self) -> AsyncIterator[MensajeMQTT]:
        """Generador async de mensajes entrantes hasta desconexión."""
        ...
        yield  # pragma: no cover - marca de protocolo


class AiomqttAdapter:
    """Adaptador del cliente real de aiomqtt al protocolo ClienteMQTT."""

    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: str = "homevault-ai",
    ) -> None:
        import aiomqtt  # import perezoso: no hace falta broker para tests

        self._client = aiomqtt.Client(
            hostname=host,
            port=port,
            username=username,
            password=password,
            identifier=client_id,
        )
        self._stack: Optional[AsyncExitStack] = None
        self._flujo: Optional[AsyncIterator] = None

    async def connect(self) -> None:
        """Abre la conexión y el flujo de mensajes con AsyncExitStack."""
        self._stack = AsyncExitStack()
        await self._stack.enter_async_context(self._client)
        flujo = await self._stack.enter_async_context(self._client.messages())
        self._flujo = flujo.__aiter__()

    async def disconnect(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self._flujo = None

    async def subscribe(self, topic: str) -> None:
        await self._client.subscribe(topic)

    async def publish(
        self, topic: str, payload: str, retain: bool = False
    ) -> None:
        await self._client.publish(topic, payload, retain=retain)

    async def messages(self) -> AsyncIterator[MensajeMQTT]:
        """Yield de mensajes normalizados hasta agotar el flujo."""
        if self._flujo is None:
            raise RuntimeError("AiomqttAdapter sin conexión (falta connect())")
        async for mensaje in self._flujo:
            yield MensajeMQTT(
                topic=str(mensaje.topic),
                payload=bytes(mensaje.payload),
            )


class MQTTConnector:
    """Puente entre el vault Markdown y el mundo MQTT/Home Assistant."""

    def __init__(
        self,
        vault: VaultManager,
        client: ClienteMQTT,
        google_sync: Any = None,
    ) -> None:
        self.vault = vault
        self.client = client
        self.google_sync = google_sync  # reservado para futuras acciones
        self._tarea_bucle: Optional[asyncio.Task] = None

    # --- Ciclo de vida (enganchar al lifespan de FastAPI) ----------------------

    async def start(self) -> None:
        """Conecta, suscribe los pesos y arranca el bucle de mensajes."""
        await self.client.connect()
        await self.client.subscribe(TOPICO_PESOS)
        self._tarea_bucle = asyncio.create_task(self._bucle_mensajes())
        logger.info("MQTTConnector iniciado, suscrito a %s", TOPICO_PESOS)

    async def stop(self) -> None:
        """Detiene el bucle de mensajes y desconecta del broker."""
        if self._tarea_bucle is not None:
            self._tarea_bucle.cancel()
            try:
                await self._tarea_bucle
            except asyncio.CancelledError:
                pass
            self._tarea_bucle = None
        await self.client.disconnect()
        logger.info("MQTTConnector detenido")

    async def _bucle_mensajes(self) -> None:
        """Consume mensajes del broker y los procesa de forma secuencial."""
        async for mensaje in self.client.messages():
            try:
                await self.procesar_mensaje_peso(mensaje.topic, mensaje.payload)
            except Exception:
                logger.exception(
                    "Error procesando mensaje MQTT de %s", mensaje.topic
                )

    # --- 1. Sensores de peso -> stock_actual -----------------------------------

    @staticmethod
    def _convertir_gramos(peso_gramos: float, unidad: str) -> Optional[float]:
        """Convierte un peso en gramos a la unidad del ítem.

        Solo hay conversión directa para ítems medidos en gramos o kg; para
        litros/unidades/pastillas/dosis no existe equivalencia sin densidad o
        peso unitario, y se devuelve None.
        """
        if unidad == "gramos":
            return peso_gramos
        if unidad == "kg":
            return round(peso_gramos / 1000.0, 6)
        return None

    @staticmethod
    def _nota_peso_crudo(cuerpo: str, peso_gramos: float) -> str:
        """Inserta o reemplaza la nota de peso crudo en el cuerpo Markdown."""
        linea = f"{_MARCA_NOTA_SENSOR} {peso_gramos} g ({ahora_utc().isoformat()})"
        lineas = cuerpo.splitlines()
        for indice, existente in enumerate(lineas):
            if existente.startswith(_MARCA_NOTA_SENSOR):
                lineas[indice] = linea
                break
        else:
            if lineas and lineas[-1].strip():
                lineas.append("")
            lineas.append(linea)
        return "\n".join(lineas) + "\n"

    async def _buscar_item_por_topico(self, topic: str) -> Optional[Consumible]:
        """Devuelve el consumible cuyo mqtt_sensor_topic coincide exactamente."""
        for item in await self.vault.list_items():
            if item.mqtt_sensor_topic == topic:
                return item
        return None

    async def procesar_mensaje_peso(
        self, topic: str, payload: bytes | str
    ) -> Optional[Consumible]:
        """Procesa una lectura de báscula y actualiza el .md del consumible.

        Devuelve el ítem actualizado, o None si el payload no es un número o
        ningún ítem tiene ese ``mqtt_sensor_topic``.
        """
        try:
            peso_gramos = float(
                payload.decode("utf-8") if isinstance(payload, bytes) else payload
            )
        except (ValueError, UnicodeDecodeError):
            logger.warning("Payload de peso no numérico en %s: %r", topic, payload)
            return None

        item = await self._buscar_item_por_topico(topic)
        if item is None:
            logger.info("Lectura de peso sin consumible asociado: %s", topic)
            return None

        path = await self.vault._find_item_path(item.id)
        if path is None:  # defensivo: list_items lo acaba de leer
            return None
        lock = await self.vault._get_lock(path)
        async with lock:
            item, cuerpo = await self.vault._read_doc(path, Consumible)
            convertido = self._convertir_gramos(peso_gramos, item.unidad)
            if convertido is not None:
                item.stock_actual = round(convertido, 6)
            else:
                cuerpo = self._nota_peso_crudo(cuerpo, peso_gramos)
            item.ultima_actualizacion = ahora_utc()
            await self.vault._write_doc(path, item, cuerpo)

        # Trigger de lista de la compra si la báscula marca bajo mínimo
        if (
            convertido is not None
            and item.stock_actual <= item.stock_minimo
            and item.auto_lista_compra
        ):
            await self.vault._add_to_shopping_list(item)

        # Republica el estado para Home Assistant
        await self.publicar_estado_item(item)
        return item

    # --- 2. MQTT Discovery para Home Assistant ----------------------------------

    @staticmethod
    def _topic_estado_item(item: Consumible) -> str:
        return f"homevault/inventario/{item.id}/stock"

    @staticmethod
    def _topic_estado_tarea(tarea: Tarea) -> str:
        return f"homevault/tareas/{tarea.id}/estado"

    async def publicar_estado_item(self, item: Consumible) -> None:
        """Publica el stock actual del ítem en su tópico de estado."""
        await self.client.publish(
            self._topic_estado_item(item), str(item.stock_actual), retain=True
        )

    async def publicar_estado_tarea(self, tarea: Tarea) -> None:
        """Publica el estado de la tarea en su tópico de estado."""
        await self.client.publish(
            self._topic_estado_tarea(tarea), tarea.estado, retain=True
        )

    async def publicar_discovery(self) -> dict[str, int]:
        """Publica configs de MQTT Discovery para HA (retain=True).

        Crea sensores para consumibles en bajo mínimo (stock_actual <=
        stock_minimo) y para tareas pendientes, y publica su estado actual.
        Devuelve un resumen {"items": N, "tareas": M}.
        """
        publicados = {"items": 0, "tareas": 0}

        for item in await self.vault.list_items():
            if item.stock_actual > item.stock_minimo:
                continue
            config = {
                "name": f"HomeVault {item.nombre}",
                "unique_id": f"homevault_{item.id}",
                "state_topic": self._topic_estado_item(item),
                "unit_of_measurement": item.unidad,
            }
            await self.client.publish(
                f"{PREFIJO_DISCOVERY}/sensor/homevault_{item.id}/config",
                json.dumps(config, ensure_ascii=False),
                retain=True,
            )
            await self.publicar_estado_item(item)
            publicados["items"] += 1

        for tarea in await self.vault.list_tasks(estado="pendiente"):
            config = {
                "name": f"HomeVault tarea {tarea.titulo}",
                "unique_id": f"homevault_tarea_{tarea.id}",
                "state_topic": self._topic_estado_tarea(tarea),
            }
            await self.client.publish(
                f"{PREFIJO_DISCOVERY}/sensor/homevault_tarea_{tarea.id}/config",
                json.dumps(config, ensure_ascii=False),
                retain=True,
            )
            await self.publicar_estado_tarea(tarea)
            publicados["tareas"] += 1

        logger.info("Discovery publicado: %s", publicados)
        return publicados

    # --- 3. Avisos matutinos por TTS ---------------------------------------------

    @staticmethod
    def _formato_dias(dias: int) -> str:
        """'hoy' / 'mañana' / 'en N días' para mensajes hablados."""
        if dias <= 0:
            return "hoy"
        if dias == 1:
            return "mañana"
        return f"en {dias} días"

    async def avisos_matutinos(self) -> str:
        """Publica en home/tts/say caducidades <48h y tareas del día.

        Las "tareas del día" son las pendientes con fecha_programada de hoy o
        anterior (incluye atrasadas), agrupadas por conviviente. Devuelve el
        mensaje publicado (útil para tests y logs).
        """
        caducan = await self.vault.query_expiring(days_ahead=2)
        hoy = ahora_utc().date()
        pendientes = [
            tarea
            for tarea in await self.vault.list_tasks(estado="pendiente")
            if tarea.fecha_programada is not None
            and tarea.fecha_programada <= hoy
        ]

        partes: list[str] = ["Buenos días."]
        if caducan:
            lista = ", ".join(
                f"{item.nombre} (caduca {self._formato_dias(item.dias_restantes)})"
                for item in caducan
            )
            partes.append(f"Alimentos que caducan en menos de 48 horas: {lista}.")
        else:
            partes.append("No hay alimentos próximos a caducar.")

        if pendientes:
            por_conviviente: dict[str, list[str]] = {}
            for tarea in pendientes:
                clave = tarea.asignado_a or "sin asignar"
                por_conviviente.setdefault(clave, []).append(tarea.titulo)
            for conviviente, titulos in sorted(por_conviviente.items()):
                partes.append(
                    f"Tareas de hoy para {conviviente}: {', '.join(titulos)}."
                )
        else:
            partes.append("No hay tareas pendientes para hoy.")

        mensaje = " ".join(partes)
        await self.client.publish(TOPICO_TTS, mensaje)
        return mensaje


def build_mqtt_connector(
    vault: VaultManager,
    settings: Settings,
    google_sync: Any = None,
    client: Optional[ClienteMQTT] = None,
) -> MQTTConnector:
    """Factoría: construye el conector con el cliente real de aiomqtt.

    Lee la configuración MQTT de las settings (campos mqtt_*); las credenciales
    vacías se normalizan a None (broker sin autenticación).
    """
    if client is None:
        client = AiomqttAdapter(
            host=settings.mqtt_host,
            port=settings.mqtt_port,
            username=settings.mqtt_username or None,
            password=settings.mqtt_password or None,
            client_id=settings.mqtt_client_id,
        )
    return MQTTConnector(vault=vault, client=client, google_sync=google_sync)
