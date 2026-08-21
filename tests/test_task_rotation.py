"""Tests del flujo complete_task: historial, rotación y reprogramación."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from backend.google_sync import GoogleSync
from backend.vault_manager import VaultManager
from conftest import (
    FakeCalendarClient,
    FakeTasksClient,
    escribir_md,
    metadata_tarea_base,
)


async def test_complete_task_historial_rotacion_y_persistencia(
    google_sync: GoogleSync, vault: VaultManager
) -> None:
    """Completar actualiza historial, rota al siguiente conviviente y persiste."""
    escribir_md(vault.vault_path, "tareas", "tarea.md", metadata_tarea_base())

    tarea = await google_sync.complete_task("tarea_test_01", completed_by="Daniel")

    hoy = datetime.now(timezone.utc).date()
    assert len(tarea.historial_completados) == 1
    assert tarea.historial_completados[0].fecha == hoy
    assert tarea.historial_completados[0].usuario == "Daniel"
    # Rotación Daniel -> Pareja
    assert tarea.indice_rotacion_actual == 1
    assert tarea.asignado_a == "Pareja"
    # Semanal: se reprograma y vuelve a pendiente
    assert tarea.estado == "pendiente"
    assert tarea.fecha_programada == date(2026, 8, 27)
    assert tarea.ultima_realizacion is not None
    assert tarea.ultima_realizacion.tzinfo is not None
    # Persistido en el .md
    persistida = await vault.get_task("tarea_test_01")
    assert persistida is not None
    assert persistida.asignado_a == "Pareja"
    assert len(persistida.historial_completados) == 1


async def test_rotacion_ciclo_completo_daniel_pareja_daniel(
    google_sync: GoogleSync, vault: VaultManager
) -> None:
    """Dos completaciones consecutivas cierran el ciclo de rotación."""
    escribir_md(vault.vault_path, "tareas", "tarea.md", metadata_tarea_base())

    primera = await google_sync.complete_task("tarea_test_01", completed_by="Daniel")
    assert primera.asignado_a == "Pareja"

    segunda = await google_sync.complete_task("tarea_test_01", completed_by="Pareja")
    assert segunda.asignado_a == "Daniel"
    assert segunda.indice_rotacion_actual == 0
    assert len(segunda.historial_completados) == 2


async def test_complete_task_marca_remoto_y_crea_siguiente_ocurrencia(
    google_sync: GoogleSync,
    vault: VaultManager,
    fake_tasks: FakeTasksClient,
    fake_calendar: FakeCalendarClient,
) -> None:
    """Se marca completada en Google y se crea la siguiente ocurrencia."""
    escribir_md(
        vault.vault_path,
        "tareas",
        "tarea.md",
        metadata_tarea_base(google_task_id="gtask_previo"),
    )
    fake_tasks.tareas["gtask_previo"] = {
        "id": "gtask_previo",
        "title": "Limpiar el baño",
        "status": "needsAction",
    }

    tarea = await google_sync.complete_task("tarea_test_01", completed_by="Daniel")

    # La ocurrencia anterior quedó completada en remoto
    assert fake_tasks.tareas["gtask_previo"]["status"] == "completed"
    # La nueva ocurrencia existe en remoto con la nueva fecha
    nuevo_id = tarea.google_task_id
    assert nuevo_id is not None and nuevo_id != "gtask_previo"
    assert fake_tasks.tareas[nuevo_id]["due"] == "2026-08-27T00:00:00.000Z"
    # Nuevo evento de Calendar con la nueva fecha
    assert tarea.google_calendar_event_id is not None
    evento = fake_calendar.eventos[tarea.google_calendar_event_id]
    assert evento["start"] == {"date": "2026-08-27"}


@pytest.mark.parametrize(
    "frecuencia, fecha_esperada",
    [
        ("diaria", date(2026, 8, 21)),
        ("semanal", date(2026, 8, 27)),
        ("quincenal", date(2026, 9, 3)),
        ("mensual", date(2026, 9, 20)),
        ("cada_3_meses", date(2026, 11, 20)),
        ("cada_6_meses", date(2027, 2, 20)),
        ("anual", date(2027, 8, 20)),
    ],
)
async def test_complete_task_reprograma_segun_frecuencia(
    google_sync: GoogleSync,
    vault: VaultManager,
    frecuencia: str,
    fecha_esperada: date,
) -> None:
    """Cada frecuencia recurrente calcula la nueva fecha y vuelve a pendiente."""
    escribir_md(
        vault.vault_path,
        "tareas",
        "tarea.md",
        metadata_tarea_base(frecuencia=frecuencia),
    )

    tarea = await google_sync.complete_task("tarea_test_01", completed_by="Daniel")

    assert tarea.fecha_programada == fecha_esperada
    assert tarea.estado == "pendiente"


async def test_complete_task_unica_no_reprograma(
    google_sync: GoogleSync,
    vault: VaultManager,
    fake_tasks: FakeTasksClient,
) -> None:
    """Frecuencia unica: queda completada, sin nueva fecha ni ocurrencia."""
    escribir_md(
        vault.vault_path,
        "tareas",
        "tarea.md",
        metadata_tarea_base(frecuencia="unica", google_task_id="gtask_unica"),
    )
    fake_tasks.tareas["gtask_unica"] = {
        "id": "gtask_unica",
        "title": "Limpiar el baño",
        "status": "needsAction",
    }
    n_tareas_antes = len(fake_tasks.tareas)

    tarea = await google_sync.complete_task("tarea_test_01", completed_by="Daniel")

    assert tarea.estado == "completada"
    assert tarea.fecha_programada == date(2026, 8, 20)
    assert len(tarea.historial_completados) == 1
    # Se marcó completada en remoto pero NO se creó siguiente ocurrencia
    assert fake_tasks.tareas["gtask_unica"]["status"] == "completed"
    assert len(fake_tasks.tareas) == n_tareas_antes


async def test_complete_task_sin_clientes_solo_local(vault: VaultManager) -> None:
    """Sin clientes de Google la lógica local funciona igual."""
    escribir_md(vault.vault_path, "tareas", "tarea.md", metadata_tarea_base())
    sync = GoogleSync(vault=vault)

    tarea = await sync.complete_task("tarea_test_01", completed_by="Daniel")

    assert tarea.asignado_a == "Pareja"
    assert tarea.estado == "pendiente"
    assert tarea.google_task_id is None
