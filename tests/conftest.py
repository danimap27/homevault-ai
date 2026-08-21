"""Fixtures de pytest: vault temporal en tmp_path con estructura completa."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from backend.google_sync import GoogleSync
from backend.vault_manager import VaultManager

# Estructura de directorios completa del vault
DIRECTORIOS_VAULT = [
    "inventario/nevera",
    "inventario/congelador",
    "inventario/despensa",
    "inventario/limpieza",
    "inventario/recambios_tecnicos",
    "inventario/botiquin",
    "recetas",
    "planificador",
    "tareas",
    "listas",
    "gastos",
    "config",
]

# Ítem controlado para tests FIFO: dos lotes con caducidades distintas
ITEM_FIFO = """---
id: "item_test_01"
nombre: "Yogur natural"
ean_barcode: "8411111111111"
categoria: "lacteos"
ubicacion: "nevera"
stock_actual: 6.0
stock_minimo: 2.0
unidad: "unidades"
precio_unitario_estimado: 0.5
fecha_caducidad_proxima: "2026-08-22"
fecha_congelacion: null
dias_max_congelador: null
lotes:
  - id_lote: "lot_01"
    cantidad: 2.0
    fecha_caducidad: "2026-08-22"
    fecha_adquisicion: "2026-08-10"
  - id_lote: "lot_02"
    cantidad: 4.0
    fecha_caducidad: "2026-08-30"
    fecha_adquisicion: "2026-08-15"
es_reserva_estrategica: false
mqtt_sensor_topic: null
dias_promedio_consumo: 3.0
ultimo_consumo: "2026-08-19T10:00:00Z"
auto_lista_compra: true
tags: [test]
ultima_actualizacion: "2026-08-19T10:00:00Z"
---

Cuerpo Markdown del yogur de prueba.
"""

# Ítem sin lotes para el test de concurrencia
ITEM_CONCURRENCIA = """---
id: "item_conc_01"
nombre: "Arroz integral"
categoria: "despensa_seca"
ubicacion: "despensa"
stock_actual: 10.0
stock_minimo: 1.0
unidad: "kg"
lotes: []
auto_lista_compra: false
ultima_actualizacion: "2026-08-19T10:00:00Z"
---

Cuerpo del arroz.
"""


def crear_estructura_vault(raiz: Path) -> None:
    """Crea la estructura de directorios completa del vault."""
    for directorio in DIRECTORIOS_VAULT:
        (raiz / directorio).mkdir(parents=True, exist_ok=True)
    (raiz / "listas" / "compra.md").write_text(
        "# Lista de la compra\n\n", encoding="utf-8"
    )


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    """Vault temporal vacío con la estructura de directorios."""
    raiz = tmp_path / "vault"
    crear_estructura_vault(raiz)
    return raiz


@pytest.fixture
def vault(vault_path: Path) -> VaultManager:
    """VaultManager sobre el vault temporal vacío."""
    return VaultManager(vault_path)


@pytest.fixture
def vault_poblado(vault: VaultManager) -> VaultManager:
    """VaultManager con los ítems de prueba ya escritos."""
    (vault.vault_path / "inventario" / "nevera" / "yogur.md").write_text(
        ITEM_FIFO, encoding="utf-8"
    )
    (vault.vault_path / "inventario" / "despensa" / "arroz.md").write_text(
        ITEM_CONCURRENCIA, encoding="utf-8"
    )
    return vault


@pytest.fixture
def vault_ejemplo() -> VaultManager:
    """Copia temporal del vault de ejemplo del repositorio."""
    import tempfile

    origen = Path(__file__).parent.parent / "vault"
    destino = Path(tempfile.mkdtemp()) / "vault"
    shutil.copytree(origen, destino)
    return VaultManager(destino)


# --- Fake del LLM para el ReceiptParser (Fase 3) --------------------------------


class FakeLLM:
    """Fake del ClienteLLM: devuelve respuestas encoladas y registra llamadas."""

    def __init__(self, respuestas: list[str] | None = None) -> None:
        self.respuestas: list[str] = list(respuestas or [])
        self.llamadas: list[dict] = []

    async def completar(
        self,
        prompt: str,
        imagen: bytes | None = None,
        mime_type: str | None = None,
    ) -> str:
        self.llamadas.append(
            {"prompt": prompt, "imagen": imagen, "mime_type": mime_type}
        )
        if not self.respuestas:
            raise AssertionError("FakeLLM sin respuestas encoladas")
        return self.respuestas.pop(0)


@pytest.fixture
def fake_llm() -> FakeLLM:
    """LLM fake vacío (encolar respuestas en cada test)."""
    return FakeLLM()


# --- Fakes de las APIs de Google (sin credenciales reales) ---------------------
class FakeTasksClient:
    """Fake del cliente de Google Tasks con la interfaz mínima de GoogleSync."""

    def __init__(self) -> None:
        self.tareas: dict[str, dict] = {}
        self._contador = 0

    def list_tasks(self, tasklist: str) -> list[dict]:
        return list(self.tareas.values())

    def insert_task(self, tasklist: str, body: dict) -> dict:
        self._contador += 1
        gid = f"gtask_{self._contador}"
        tarea = {"id": gid, "status": "needsAction", **body}
        self.tareas[gid] = tarea
        return tarea

    def patch_task(self, tasklist: str, task_id: str, body: dict) -> dict:
        self.tareas[task_id].update(body)
        return self.tareas[task_id]


class FakeCalendarClient:
    """Fake del cliente de Google Calendar."""

    def __init__(self) -> None:
        self.eventos: dict[str, dict] = {}
        self._contador = 0

    def insert_event(self, calendar_id: str, body: dict) -> dict:
        self._contador += 1
        eid = f"gevent_{self._contador}"
        self.eventos[eid] = {"id": eid, **body}
        return self.eventos[eid]


# --- Helpers de escritura de documentos del vault ------------------------------


def escribir_md(vault_path: Path, subdir: str, nombre: str, metadata: dict) -> Path:
    """Escribe un documento Markdown con frontmatter YAML en el vault."""
    ruta = vault_path / subdir / nombre
    texto = (
        "---\n"
        + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
        + "---\n\nCuerpo de prueba.\n"
    )
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def metadata_tarea_base(**overrides) -> dict:
    """Frontmatter base de una tarea recurrente Daniel/Pareja."""
    metadata = {
        "id": "tarea_test_01",
        "titulo": "Limpiar el baño",
        "zona": "bano",
        "frecuencia": "semanal",
        "estado": "pendiente",
        "asignado_a": "Daniel",
        "rotacion_convivientes": ["Daniel", "Pareja"],
        "indice_rotacion_actual": 0,
        "prioridad": "media",
        "consumibles_requeridos": [],
        "fecha_programada": "2026-08-20",
    }
    metadata.update(overrides)
    return metadata


def metadata_item_limpieza(**overrides) -> dict:
    """Frontmatter base de un consumible de limpieza."""
    metadata = {
        "id": "item_lejia",
        "nombre": "Lejía concentrada",
        "categoria": "limpieza",
        "ubicacion": "bano",
        "stock_actual": 5.0,
        "stock_minimo": 1.0,
        "unidad": "unidades",
        "auto_lista_compra": True,
    }
    metadata.update(overrides)
    return metadata


@pytest.fixture
def fake_tasks() -> FakeTasksClient:
    """Cliente fake de Google Tasks."""
    return FakeTasksClient()


@pytest.fixture
def fake_calendar() -> FakeCalendarClient:
    """Cliente fake de Google Calendar."""
    return FakeCalendarClient()


@pytest.fixture
def google_sync(
    vault: VaultManager,
    fake_tasks: FakeTasksClient,
    fake_calendar: FakeCalendarClient,
) -> GoogleSync:
    """GoogleSync sobre vault temporal con clientes fake inyectados."""
    return GoogleSync(
        vault=vault,
        tasks_client=fake_tasks,
        calendar_client=fake_calendar,
        tasks_list_id="lista_test",
        calendar_id="cal_test",
    )
