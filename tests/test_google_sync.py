"""Tests de GoogleSync: creación en Google, polling y check de consumibles.

Sin credenciales reales: se inyectan los fakes FakeTasksClient y
FakeCalendarClient (definidos en conftest.py) en el GoogleSync.
"""

from __future__ import annotations

from datetime import date

from backend.google_sync import GoogleSync
from backend.vault_manager import VaultManager
from conftest import (
    FakeCalendarClient,
    FakeTasksClient,
    escribir_md,
    metadata_item_limpieza,
    metadata_tarea_base,
)


async def test_crear_tarea_persiste_ids_google(
    google_sync: GoogleSync, vault: VaultManager, fake_calendar: FakeCalendarClient
) -> None:
    """Crear en Google persiste google_task_id y google_calendar_event_id."""
    escribir_md(vault.vault_path, "tareas", "tarea.md", metadata_tarea_base())
    tarea = await vault.get_task("tarea_test_01")
    assert tarea is not None

    await google_sync.create_task_in_google(tarea)

    assert tarea.google_task_id == "gtask_1"
    assert tarea.google_calendar_event_id == "gevent_1"
    # Los ids quedan persistidos en el .md (fuente de verdad)
    persistida = await vault.get_task("tarea_test_01")
    assert persistida is not None
    assert persistida.google_task_id == "gtask_1"
    assert persistida.google_calendar_event_id == "gevent_1"
    # El evento remoto es de día completo con la fecha programada
    evento = fake_calendar.eventos["gevent_1"]
    assert evento["start"] == {"date": "2026-08-20"}


async def test_crear_tarea_sin_fecha_no_crea_evento(
    google_sync: GoogleSync,
    vault: VaultManager,
    fake_calendar: FakeCalendarClient,
) -> None:
    """Sin fecha_programada no se crea evento de Calendar."""
    escribir_md(
        vault.vault_path,
        "tareas",
        "tarea.md",
        metadata_tarea_base(fecha_programada=None),
    )
    tarea = await vault.get_task("tarea_test_01")
    assert tarea is not None

    await google_sync.create_task_in_google(tarea)

    assert tarea.google_task_id == "gtask_1"
    assert tarea.google_calendar_event_id is None
    assert fake_calendar.eventos == {}


async def test_poll_dispara_flujo_exactamente_una_vez(
    google_sync: GoogleSync,
    vault: VaultManager,
    fake_tasks: FakeTasksClient,
) -> None:
    """Una tarea completada en remoto dispara el flujo local una sola vez."""
    escribir_md(
        vault.vault_path,
        "tareas",
        "tarea.md",
        metadata_tarea_base(google_task_id="gtask_remota_1"),
    )
    fake_tasks.tareas["gtask_remota_1"] = {
        "id": "gtask_remota_1",
        "title": "Limpiar el baño",
        "status": "completed",
    }

    procesadas = await google_sync.poll_google_tasks()
    assert procesadas == ["tarea_test_01"]

    # El flujo local se ejecutó: historial, rotación y reprogramación
    tarea = await vault.get_task("tarea_test_01")
    assert tarea is not None
    assert len(tarea.historial_completados) == 1
    assert tarea.asignado_a == "Pareja"
    assert tarea.estado == "pendiente"
    assert tarea.fecha_programada == date(2026, 8, 27)
    # El id de Google apunta a la nueva ocurrencia
    assert tarea.google_task_id != "gtask_remota_1"

    # Segundo polling: no vuelve a disparar el flujo
    assert await google_sync.poll_google_tasks() == []
    tarea = await vault.get_task("tarea_test_01")
    assert tarea is not None
    assert len(tarea.historial_completados) == 1


async def test_poll_ignora_tareas_no_completadas_o_desconocidas(
    google_sync: GoogleSync,
    vault: VaultManager,
    fake_tasks: FakeTasksClient,
) -> None:
    """El polling ignora needsAction y tareas remotas sin reflejo local."""
    escribir_md(
        vault.vault_path,
        "tareas",
        "tarea.md",
        metadata_tarea_base(google_task_id="gtask_local"),
    )
    fake_tasks.tareas["gtask_local"] = {
        "id": "gtask_local",
        "status": "needsAction",
    }
    fake_tasks.tareas["gtask_ajena"] = {
        "id": "gtask_ajena",
        "status": "completed",
    }

    assert await google_sync.poll_google_tasks() == []


async def test_check_consumibles_stock_suficiente_no_bloquea(
    google_sync: GoogleSync, vault: VaultManager
) -> None:
    """Con stock suficiente la tarea no queda bloqueada."""
    escribir_md(
        vault.vault_path,
        "inventario/limpieza",
        "lejia.md",
        metadata_item_limpieza(stock_actual=5.0),
    )
    escribir_md(
        vault.vault_path,
        "tareas",
        "tarea.md",
        metadata_tarea_base(
            consumibles_requeridos=[
                {
                    "item_id": "item_lejia",
                    "cantidad": 1.0,
                    "unidad": "unidades",
                    "verificar_stock_previo": True,
                }
            ]
        ),
    )

    tarea = await google_sync.check_consumables_before_task("tarea_test_01")

    assert tarea.bloqueada_por_stock is False
    # No se añadió nada a la lista de la compra
    assert await vault.get_shopping_list() == []


async def test_check_consumibles_sin_stock_bloquea_y_agrega_a_lista(
    google_sync: GoogleSync, vault: VaultManager
) -> None:
    """Sin stock: añade a listas/compra.md y marca bloqueada_por_stock."""
    escribir_md(
        vault.vault_path,
        "inventario/limpieza",
        "lejia.md",
        metadata_item_limpieza(stock_actual=0.5),
    )
    escribir_md(
        vault.vault_path,
        "tareas",
        "tarea.md",
        metadata_tarea_base(
            consumibles_requeridos=[
                {
                    "item_id": "item_lejia",
                    "cantidad": 1.0,
                    "unidad": "unidades",
                    "verificar_stock_previo": True,
                }
            ]
        ),
    )

    tarea = await google_sync.check_consumables_before_task("tarea_test_01")

    assert tarea.bloqueada_por_stock is True
    # Persistido en el .md
    persistida = await vault.get_task("tarea_test_01")
    assert persistida is not None
    assert persistida.bloqueada_por_stock is True
    # El recambio está pendiente en la lista de la compra
    entradas = await vault.get_shopping_list()
    assert len(entradas) == 1
    assert entradas[0].item_id == "item_lejia"
    assert entradas[0].comprado is False


async def test_check_consumibles_sin_verificacion_no_bloquea(
    google_sync: GoogleSync, vault: VaultManager
) -> None:
    """Consumibles con verificar_stock_previo=false no bloquean la tarea."""
    escribir_md(
        vault.vault_path,
        "inventario/limpieza",
        "lejia.md",
        metadata_item_limpieza(stock_actual=0.0),
    )
    escribir_md(
        vault.vault_path,
        "tareas",
        "tarea.md",
        metadata_tarea_base(
            consumibles_requeridos=[
                {
                    "item_id": "item_lejia",
                    "cantidad": 3.0,
                    "unidad": "unidades",
                    "verificar_stock_previo": False,
                }
            ]
        ),
    )

    tarea = await google_sync.check_consumables_before_task("tarea_test_01")

    assert tarea.bloqueada_por_stock is False
