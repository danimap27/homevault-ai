"""Tests del MQTTConnector (Fase 4a) con broker MQTT fake.

Sin conexiones reales: FakeMQTTClient implementa el protocolo ClienteMQTT
(connect/disconnect/subscribe/publish/messages) con una cola asyncio.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.google_sync import GoogleSync
from backend.mqtt_connector import (
    TOPICO_PESOS,
    TOPICO_TTS,
    MensajeMQTT,
    MQTTConnector,
)
from backend.vault_manager import VaultManager
from conftest import escribir_md, metadata_item_limpieza, metadata_tarea_base


class FakeMQTTClient:
    """Broker fake: registra suscripciones/publicaciones y encola mensajes."""

    def __init__(self) -> None:
        self.conectado = False
        self.suscripciones: list[str] = []
        self.publicados: list[tuple[str, str, bool]] = []
        self._cola: asyncio.Queue[MensajeMQTT] = asyncio.Queue()

    async def connect(self) -> None:
        self.conectado = True

    async def disconnect(self) -> None:
        self.conectado = False

    async def subscribe(self, topic: str) -> None:
        self.suscripciones.append(topic)

    async def publish(
        self, topic: str, payload: str, retain: bool = False
    ) -> None:
        self.publicados.append((topic, payload, retain))

    async def messages(self):
        while True:
            yield await self._cola.get()

    def inyectar(self, topic: str, payload: str) -> None:
        """Simula la llegada de un mensaje del broker."""
        self._cola.put_nowait(MensajeMQTT(topic, payload.encode("utf-8")))


@pytest.fixture
def broker() -> FakeMQTTClient:
    return FakeMQTTClient()


@pytest.fixture
def conector(vault: VaultManager, broker: FakeMQTTClient) -> MQTTConnector:
    return MQTTConnector(vault=vault, client=broker)


def metadata_item_sensor(**overrides) -> dict:
    """Frontmatter base de un consumible con báscula MQTT."""
    metadata = {
        "id": "item_cafe",
        "nombre": "Café molido",
        "categoria": "despensa_seca",
        "ubicacion": "despensa",
        "stock_actual": 250.0,
        "stock_minimo": 100.0,
        "unidad": "gramos",
        "mqtt_sensor_topic": "home/sensors/cocina/bascula_cafe/weight",
        "auto_lista_compra": True,
    }
    metadata.update(overrides)
    return metadata


async def _esperar(condicion, timeout: float = 2.0) -> None:
    """Espera activa hasta que la condición async se cumpla (o timeout)."""
    limite = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < limite:
        if await condicion():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Timeout esperando la condición del bucle MQTT")


# --- Ciclo de vida ------------------------------------------------------------


async def test_start_suscribe_pesos_y_stop_desconecta(
    conector: MQTTConnector, broker: FakeMQTTClient
) -> None:
    """start() conecta y suscribe el comodín de pesos; stop() desconecta."""
    await conector.start()
    assert broker.conectado
    assert broker.suscripciones == [TOPICO_PESOS]
    await conector.stop()
    assert not broker.conectado


async def test_bucle_procesa_mensaje_en_segundo_plano(
    conector: MQTTConnector, broker: FakeMQTTClient, vault: VaultManager
) -> None:
    """El bucle en background actualiza el stock al llegar un peso."""
    escribir_md(
        vault.vault_path,
        "inventario/despensa",
        "cafe.md",
        metadata_item_sensor(),
    )
    await conector.start()
    broker.inyectar("home/sensors/cocina/bascula_cafe/weight", "180.5")

    async def stock_actualizado() -> bool:
        item = await vault.get_item("item_cafe")
        return item is not None and item.stock_actual == 180.5

    await _esperar(stock_actualizado)
    await conector.stop()


# --- 1. Sensores de peso ------------------------------------------------------


async def test_peso_en_gramos_actualiza_stock(
    conector: MQTTConnector, vault: VaultManager
) -> None:
    """Unidad 'gramos': el stock pasa a ser el peso leído (lectura absoluta)."""
    escribir_md(
        vault.vault_path,
        "inventario/despensa",
        "cafe.md",
        metadata_item_sensor(),
    )
    item = await conector.procesar_mensaje_peso(
        "home/sensors/cocina/bascula_cafe/weight", b"300"
    )
    assert item is not None
    assert item.stock_actual == 300.0
    persistido = await vault.get_item("item_cafe")
    assert persistido is not None
    assert persistido.stock_actual == 300.0
    assert persistido.ultima_actualizacion is not None


async def test_peso_en_kg_convierte_gramos(
    conector: MQTTConnector, vault: VaultManager
) -> None:
    """Unidad 'kg': el payload en gramos se divide entre 1000."""
    escribir_md(
        vault.vault_path,
        "inventario/despensa",
        "arroz.md",
        metadata_item_sensor(
            id="item_arroz_bascula",
            nombre="Arroz a granel",
            unidad="kg",
            mqtt_sensor_topic="home/sensors/despensa/bascula_arroz/weight",
        ),
    )
    item = await conector.procesar_mensaje_peso(
        "home/sensors/despensa/bascula_arroz/weight", "2350"
    )
    assert item is not None
    assert item.stock_actual == 2.35


async def test_peso_sin_conversion_guarda_nota_en_cuerpo(
    conector: MQTTConnector, vault: VaultManager
) -> None:
    """Sin conversión (p. ej. 'unidades'), el peso crudo queda en notas."""
    ruta = escribir_md(
        vault.vault_path,
        "inventario/despensa",
        "capsulas.md",
        metadata_item_sensor(
            id="item_capsulas",
            nombre="Cápsulas de café",
            unidad="unidades",
            mqtt_sensor_topic="home/sensors/cocina/bascula_capsulas/weight",
        ),
    )
    item = await conector.procesar_mensaje_peso(
        "home/sensors/cocina/bascula_capsulas/weight", "523"
    )
    assert item is not None
    assert item.stock_actual == 250.0  # intacto: no hay conversión
    cuerpo = ruta.read_text(encoding="utf-8")
    assert "> Sensor MQTT: 523.0 g" in cuerpo

    # Una segunda lectura reemplaza la nota, no la duplica
    await conector.procesar_mensaje_peso(
        "home/sensors/cocina/bascula_capsulas/weight", "410"
    )
    cuerpo = ruta.read_text(encoding="utf-8")
    assert "> Sensor MQTT: 410.0 g" in cuerpo
    assert cuerpo.count("> Sensor MQTT:") == 1


async def test_peso_bajo_minimo_dispara_lista_compra(
    conector: MQTTConnector, vault: VaultManager
) -> None:
    """Si la báscula deja el stock bajo el mínimo, se añade a la lista."""
    escribir_md(
        vault.vault_path,
        "inventario/despensa",
        "cafe.md",
        metadata_item_sensor(),
    )
    item = await conector.procesar_mensaje_peso(
        "home/sensors/cocina/bascula_cafe/weight", "50"
    )
    assert item is not None
    assert item.stock_actual == 50.0  # <= stock_minimo (100)
    entradas = await vault.get_shopping_list()
    assert any(e.item_id == "item_cafe" and not e.comprado for e in entradas)


async def test_topico_sin_item_no_revienta(
    conector: MQTTConnector, vault: VaultManager
) -> None:
    """Un tópico sin consumible asociado se ignora sin error."""
    resultado = await conector.procesar_mensaje_peso(
        "home/sensors/nadie/desconocido/weight", "100"
    )
    assert resultado is None


async def test_payload_no_numerico_se_descarta(
    conector: MQTTConnector, vault: VaultManager
) -> None:
    """Un payload que no es un peso en gramos no modifica nada."""
    escribir_md(
        vault.vault_path,
        "inventario/despensa",
        "cafe.md",
        metadata_item_sensor(),
    )
    resultado = await conector.procesar_mensaje_peso(
        "home/sensors/cocina/bascula_cafe/weight", "OFF"
    )
    assert resultado is None
    item = await vault.get_item("item_cafe")
    assert item is not None
    assert item.stock_actual == 250.0


# --- 2. MQTT Discovery ---------------------------------------------------------


async def test_discovery_publica_items_bajo_minimo_y_tareas(
    conector: MQTTConnector, broker: FakeMQTTClient, vault: VaultManager
) -> None:
    """Solo items con stock <= mínimo y tareas pendientes generan sensores."""
    escribir_md(
        vault.vault_path,
        "inventario/despensa",
        "cafe.md",
        metadata_item_sensor(stock_actual=80.0),  # bajo mínimo (100)
    )
    escribir_md(
        vault.vault_path,
        "inventario/botiquin",
        "lejia.md",
        metadata_item_limpieza(),  # stock 5 > mínimo 1: no sale
    )
    escribir_md(
        vault.vault_path, "tareas", "tarea.md", metadata_tarea_base()
    )
    escribir_md(
        vault.vault_path,
        "tareas",
        "tarea_hecha.md",
        metadata_tarea_base(id="tarea_hecha", estado="completada"),
    )

    resumen = await conector.publicar_discovery()
    assert resumen == {"items": 1, "tareas": 1}

    configs = {
        topic: payload
        for topic, payload, retain in broker.publicados
        if topic.endswith("/config")
    }
    config_item = json.loads(configs["homeassistant/sensor/homevault_item_cafe/config"])
    assert config_item["unique_id"] == "homevault_item_cafe"
    assert config_item["state_topic"] == "homevault/inventario/item_cafe/stock"
    assert config_item["unit_of_measurement"] == "gramos"
    config_tarea = json.loads(
        configs["homeassistant/sensor/homevault_tarea_tarea_test_01/config"]
    )
    assert config_tarea["state_topic"] == "homevault/tareas/tarea_test_01/estado"

    # Los estados se publican con retain
    estados = {
        topic: (payload, retain)
        for topic, payload, retain in broker.publicados
        if not topic.endswith("/config")
    }
    assert estados["homevault/inventario/item_cafe/stock"] == ("80.0", True)
    assert estados["homevault/tareas/tarea_test_01/estado"] == ("pendiente", True)
    # Ni el ítem con stock suficiente ni la tarea completada aparecen
    assert not any("item_lejia" in topic for topic in configs)
    assert not any("tarea_hecha" in topic for topic in configs)


# --- 3. Avisos matutinos -------------------------------------------------------


async def test_avisos_matutinos_publica_caducidades_y_tareas(
    conector: MQTTConnector, broker: FakeMQTTClient, vault: VaultManager
) -> None:
    """El TTS incluye caducidades <48h y tareas del día por conviviente."""
    manana = (date.today() + timedelta(days=1)).isoformat()
    hoy = date.today().isoformat()
    escribir_md(
        vault.vault_path,
        "inventario/nevera",
        "yogur.md",
        metadata_item_sensor(
            id="item_yogur",
            nombre="Yogur natural",
            categoria="lacteos",
            ubicacion="nevera",
            unidad="unidades",
            mqtt_sensor_topic=None,
            fecha_caducidad_proxima=manana,
        ),
    )
    # Ítem que caduca de aquí a una semana: no debe salir
    lejana = (date.today() + timedelta(days=7)).isoformat()
    escribir_md(
        vault.vault_path,
        "inventario/nevera",
        "mantequilla.md",
        metadata_item_sensor(
            id="item_mantequilla",
            nombre="Mantequilla",
            categoria="lacteos",
            ubicacion="nevera",
            unidad="gramos",
            mqtt_sensor_topic=None,
            fecha_caducidad_proxima=lejana,
        ),
    )
    escribir_md(
        vault.vault_path,
        "tareas",
        "tarea_hoy.md",
        metadata_tarea_base(fecha_programada=hoy, asignado_a="Daniel"),
    )
    escribir_md(
        vault.vault_path,
        "tareas",
        "tarea_futura.md",
        metadata_tarea_base(
            id="tarea_futura",
            titulo="Tarea de la semana que viene",
            fecha_programada=lejana,
        ),
    )

    mensaje = await conector.avisos_matutinos()

    assert (TOPICO_TTS, mensaje, False) in broker.publicados
    assert "Yogur natural" in mensaje
    assert "mañana" in mensaje
    assert "Mantequilla" not in mensaje
    assert "Daniel" in mensaje
    assert "Limpiar el baño" in mensaje
    assert "semana que viene" not in mensaje


async def test_avisos_matutinos_sin_nada_pendiente(
    conector: MQTTConnector, broker: FakeMQTTClient
) -> None:
    """Sin caducidades ni tareas, el mensaje lo dice explícitamente."""
    mensaje = await conector.avisos_matutinos()
    assert "No hay alimentos" in mensaje
    assert "No hay tareas" in mensaje
    assert broker.publicados[-1][0] == TOPICO_TTS
