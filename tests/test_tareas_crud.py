"""Tests del CRUD de tareas y la vista de calendario."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from conftest import escribir_md, metadata_tarea_base


@pytest.fixture
def cliente(vault_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient con vault temporal para tests de tareas."""
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    with TestClient(app) as cliente:
        yield cliente


def test_crear_tarea_genera_id(cliente: TestClient) -> None:
    """POST /api/tasks crea una tarea con id automático."""
    cuerpo = {
        "titulo": "Limpiar cocina",
        "zona": "cocina",
        "frecuencia": "diaria",
        "prioridad": "alta",
        "asignado_a": "Daniel",
        "fecha_programada": "2026-08-21",
    }
    respuesta = cliente.post("/api/tasks", json=cuerpo)
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["titulo"] == "Limpiar cocina"
    assert datos["id"].startswith("task_limpiar-cocina_")
    assert datos["estado"] == "pendiente"
    assert datos["rotacion_convivientes"] == ["Daniel"]
    assert datos["bloqueada_por_stock"] is False


def test_crear_tarea_con_id_explicito(cliente: TestClient) -> None:
    """Se puede forzar el id de la tarea."""
    cuerpo = {
        "id": "task_custom_01",
        "titulo": "Custom",
        "asignado_a": "Pareja",
    }
    respuesta = cliente.post("/api/tasks", json=cuerpo)
    assert respuesta.status_code == 201
    assert respuesta.json()["id"] == "task_custom_01"


def test_obtener_tarea(cliente: TestClient, vault_path: Path) -> None:
    """GET /api/tasks/{id} devuelve la tarea existente."""
    escribir_md(vault_path, "tareas", "tarea.md", metadata_tarea_base())

    respuesta = cliente.get("/api/tasks/tarea_test_01")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["id"] == "tarea_test_01"
    assert datos["titulo"] == "Limpiar el baño"


def test_obtener_tarea_inexistente(cliente: TestClient) -> None:
    """GET de una tarea inexistente devuelve 404."""
    respuesta = cliente.get("/api/tasks/no_existe")
    assert respuesta.status_code == 404


def test_actualizar_tarea_preserva_cuerpo(
    cliente: TestClient, vault_path: Path
) -> None:
    """PUT actualiza campos editables y preserva el cuerpo Markdown."""
    escribir_md(vault_path, "tareas", "tarea.md", metadata_tarea_base())
    ruta = vault_path / "tareas" / "tarea.md"
    cuerpo_original = ruta.read_text(encoding="utf-8")
    assert "Cuerpo de prueba" in cuerpo_original

    respuesta = cliente.put(
        "/api/tasks/tarea_test_01",
        json={
            "titulo": "Limpiar el baño grande",
            "prioridad": "urgente",
            "asignado_a": "Pareja",
        },
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["titulo"] == "Limpiar el baño grande"
    assert datos["prioridad"] == "urgente"
    assert datos["asignado_a"] == "Pareja"
    # Campos no editables se preservan
    assert datos["estado"] == "pendiente"
    assert datos["historial_completados"] == []
    # El cuerpo Markdown sigue intacto
    cuerpo_final = ruta.read_text(encoding="utf-8")
    assert "Cuerpo de prueba" in cuerpo_final


def test_borrar_tarea(cliente: TestClient, vault_path: Path) -> None:
    """DELETE /api/tasks/{id} elimina el archivo .md."""
    escribir_md(vault_path, "tareas", "tarea.md", metadata_tarea_base())

    respuesta = cliente.delete("/api/tasks/tarea_test_01")
    assert respuesta.status_code == 204
    assert not (vault_path / "tareas" / "tarea.md").exists()


def test_borrar_tarea_inexistente(cliente: TestClient) -> None:
    """DELETE de tarea inexistente devuelve 404."""
    respuesta = cliente.delete("/api/tasks/no_existe")
    assert respuesta.status_code == 404


def test_calendario_tarea_unica(cliente: TestClient, vault_path: Path) -> None:
    """Una tarea única aparece una sola vez si su fecha está en rango."""
    escribir_md(
        vault_path,
        "tareas",
        "tarea.md",
        metadata_tarea_base(frecuencia="unica", fecha_programada="2026-08-21"),
    )

    respuesta = cliente.get(
        "/api/tasks/calendar",
        params={"from": "2026-08-20", "to": "2026-08-25"},
    )
    assert respuesta.status_code == 200
    vistas = respuesta.json()
    assert len(vistas) == 1
    assert vistas[0]["task_id"] == "tarea_test_01"
    assert vistas[0]["fecha"] == "2026-08-21"


def test_calendario_tarea_diaria_7_dias(
    cliente: TestClient, vault_path: Path
) -> None:
    """Una tarea diaria genera 7 ocurrencias en una semana."""
    escribir_md(
        vault_path,
        "tareas",
        "tarea.md",
        metadata_tarea_base(frecuencia="diaria", fecha_programada="2026-08-21"),
    )

    respuesta = cliente.get(
        "/api/tasks/calendar",
        params={"from": "2026-08-21", "to": "2026-08-27"},
    )
    assert respuesta.status_code == 200
    vistas = respuesta.json()
    assert len(vistas) == 7
    fechas = [v["fecha"] for v in vistas]
    assert fechas == [
        "2026-08-21",
        "2026-08-22",
        "2026-08-23",
        "2026-08-24",
        "2026-08-25",
        "2026-08-26",
        "2026-08-27",
    ]


def test_calendario_tarea_semanal_4_ocurrencias(
    cliente: TestClient, vault_path: Path
) -> None:
    """Una tarea semanal genera 4 ocurrencias en un mes."""
    escribir_md(
        vault_path,
        "tareas",
        "tarea.md",
        metadata_tarea_base(frecuencia="semanal", fecha_programada="2026-08-21"),
    )

    respuesta = cliente.get(
        "/api/tasks/calendar",
        params={"from": "2026-08-21", "to": "2026-09-17"},
    )
    assert respuesta.status_code == 200
    vistas = respuesta.json()
    assert len(vistas) == 4
    fechas = [v["fecha"] for v in vistas]
    assert fechas == [
        "2026-08-21",
        "2026-08-28",
        "2026-09-04",
        "2026-09-11",
    ]


def test_calendario_rango_invertido(cliente: TestClient) -> None:
    """El calendario rechaza rangos invertidos."""
    respuesta = cliente.get(
        "/api/tasks/calendar",
        params={"from": "2026-08-27", "to": "2026-08-21"},
    )
    assert respuesta.status_code == 400
