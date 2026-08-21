"""Tests del router de domótica (Fase 4a): webhook de botones físicos.

Se monta una app FastAPI mínima con el router (main.py no se toca) y se
inyectan en app.state el vault temporal, un GoogleSync con clientes fake y,
opcionalmente, el dict de botones. Se usa httpx.AsyncClient para compartir
el bucle de eventos con el VaultManager async.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI

from backend.google_sync import GoogleSync
from backend.routers.domotica import router
from backend.vault_manager import VaultManager
from conftest import (
    FakeCalendarClient,
    FakeTasksClient,
    escribir_md,
    metadata_item_limpieza,
    metadata_tarea_base,
)

BOTONES_TEST = {
    "boton_cocina": {
        "descripcion": "Botón junto a la nevera",
        "acciones": {
            "simple": {
                "tipo": "consumir_item",
                "item_id": "item_lejia",
                "cantidad": 1.0,
            },
            "doble": {"tipo": "completar_tarea", "task_id": "tarea_test_01"},
        },
    }
}


@pytest.fixture
def app_domotica(vault: VaultManager) -> FastAPI:
    """App mínima con el router y las dependencias en app.state."""
    app = FastAPI()
    app.include_router(router)
    app.state.vault = vault
    app.state.google_sync = GoogleSync(
        vault=vault,
        tasks_client=FakeTasksClient(),
        calendar_client=FakeCalendarClient(),
    )
    app.state.botones_config = BOTONES_TEST
    return app


async def _post_boton(app: FastAPI, boton_id: str, accion: str) -> httpx.Response:
    """POST al webhook de botones contra la app en memoria."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as cliente:
        return await cliente.post(
            "/api/domotica/webhook/boton",
            json={"boton_id": boton_id, "accion": accion},
        )


async def test_boton_consumir_item_descuenta_una_unidad(
    app_domotica: FastAPI,
) -> None:
    """La acción consumir_item descuenta 1 unidad vía motor FIFO."""
    vault: VaultManager = app_domotica.state.vault
    escribir_md(
        vault.vault_path, "inventario/botiquin", "lejia.md",
        metadata_item_limpieza(),
    )

    respuesta = await _post_boton(app_domotica, "boton_cocina", "simple")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "consumir_item"
    assert cuerpo["resultado_consumo"]["stock_actual"] == 4.0

    # Persistido en el .md (fuente de verdad)
    item = await vault.get_item("item_lejia")
    assert item is not None
    assert item.stock_actual == 4.0


async def test_boton_completar_tarea_via_google_sync(
    app_domotica: FastAPI,
) -> None:
    """La acción completar_tarea usa GoogleSync.complete_task."""
    vault: VaultManager = app_domotica.state.vault
    escribir_md(
        vault.vault_path, "tareas", "tarea.md", metadata_tarea_base()
    )

    respuesta = await _post_boton(app_domotica, "boton_cocina", "doble")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "completar_tarea"
    tarea = cuerpo["tarea_completada"]
    # Tarea semanal: queda reprogramada y rota el conviviente
    assert tarea["estado"] == "pendiente"
    assert tarea["fecha_programada"] == "2026-08-27"
    assert tarea["asignado_a"] == "Pareja"
    # El historial registra qué botón la completó
    assert tarea["historial_completados"][0]["usuario"] == "boton_cocina"


async def test_boton_desconocido_devuelve_404(app_domotica: FastAPI) -> None:
    respuesta = await _post_boton(app_domotica, "boton_inexistente", "simple")
    assert respuesta.status_code == 404


async def test_accion_desconocida_devuelve_404(app_domotica: FastAPI) -> None:
    respuesta = await _post_boton(app_domotica, "boton_cocina", "mantener")
    assert respuesta.status_code == 404


async def test_item_inexistente_devuelve_404(app_domotica: FastAPI) -> None:
    """consumir_item sobre un item_id que no está en el vault da 404."""
    app_domotica.state.botones_config = {
        "b1": {"acciones": {"simple": {"tipo": "consumir_item",
                                       "item_id": "item_fantasma"}}}
    }
    respuesta = await _post_boton(app_domotica, "b1", "simple")
    assert respuesta.status_code == 404


async def test_tipo_accion_desconocido_devuelve_400(
    app_domotica: FastAPI,
) -> None:
    app_domotica.state.botones_config = {
        "b2": {"acciones": {"simple": {"tipo": "encender_luz"}}}
    }
    respuesta = await _post_boton(app_domotica, "b2", "simple")
    assert respuesta.status_code == 400


async def test_carga_botones_desde_json_del_vault(
    app_domotica: FastAPI,
) -> None:
    """Sin dict inyectado, el mapa se lee de config/botones.json del vault."""
    vault: VaultManager = app_domotica.state.vault
    app_domotica.state.botones_config = None
    (vault.vault_path / "config" / "botones.json").write_text(
        json.dumps(BOTONES_TEST), encoding="utf-8"
    )
    escribir_md(
        vault.vault_path, "inventario/botiquin", "lejia.md",
        metadata_item_limpieza(),
    )
    respuesta = await _post_boton(app_domotica, "boton_cocina", "simple")
    assert respuesta.status_code == 200
    assert respuesta.json()["resultado_consumo"]["stock_actual"] == 4.0


async def test_botones_json_corrupto_devuelve_500(
    app_domotica: FastAPI,
) -> None:
    """Un config/botones.json inválido se reporta como 500, no como crash."""
    vault: VaultManager = app_domotica.state.vault
    app_domotica.state.botones_config = None
    (vault.vault_path / "config" / "botones.json").write_text(
        "{no es json", encoding="utf-8"
    )
    respuesta = await _post_boton(app_domotica, "boton_cocina", "simple")
    assert respuesta.status_code == 500
