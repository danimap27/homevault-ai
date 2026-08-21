"""Tests de integración: app FastAPI completa contra un vault temporal.

El lifespan se ejecuta con VAULT_PATH apuntando al vault temporal de
tmp_path (fixture de conftest); los servicios externos (Google, IA, MQTT e
impresora) quedan deshabilitados por defecto.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from conftest import escribir_md, metadata_tarea_base

# Receta mínima válida según el esquema B de backend/models.py
_METADATA_RECETA = {
    "id": "recipe_test_01",
    "titulo": "Lentejas de prueba",
    "categoria": "comida",
    "tiempo_minutos": 40,
    "raciones": 4,
    "calorias_racion": None,
    "ingredientes": [],
    "tags": ["test"],
}


@pytest.fixture
def cliente(vault_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient de la app completa con el vault temporal."""
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    with TestClient(app) as cliente:
        yield cliente


def test_inventario_responde(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/inventory")
    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_recipes(cliente: TestClient, vault_path: Path) -> None:
    escribir_md(vault_path, "recetas", "lentejas.md", _METADATA_RECETA)
    respuesta = cliente.get("/api/recipes")
    assert respuesta.status_code == 200
    recetas = respuesta.json()
    assert [r["id"] for r in recetas] == ["recipe_test_01"]


def test_planner_rescue_vacio(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/planner/rescue", params={"dias": 4})
    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_barcode_503_sin_off(cliente: TestClient) -> None:
    """Sin OFFClient en app.state el escaneo de EAN desconocido da 503."""
    cliente.app.state.off_client = None
    respuesta = cliente.get("/api/barcode/0000000000000")
    assert respuesta.status_code == 503


def test_location(cliente: TestClient, vault_path: Path) -> None:
    (vault_path / "config" / "ubicaciones.json").write_text(
        json.dumps(
            {
                "ubicaciones": [
                    {"id": "nevera", "nombre": "Nevera", "tipo": "frio"}
                ]
            }
        ),
        encoding="utf-8",
    )
    respuesta = cliente.get("/location/nevera")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["slug"] == "nevera"
    assert cuerpo["items"] == []


def test_tasks_filtro_estado(cliente: TestClient, vault_path: Path) -> None:
    escribir_md(vault_path, "tareas", "tarea1.md", metadata_tarea_base())
    escribir_md(
        vault_path,
        "tareas",
        "tarea2.md",
        metadata_tarea_base(id="tarea_test_02", estado="completada"),
    )
    completadas = cliente.get("/api/tasks", params={"estado": "completada"})
    assert completadas.status_code == 200
    assert [t["id"] for t in completadas.json()] == ["tarea_test_02"]
    pendientes = cliente.get("/api/tasks", params={"estado": "pendiente"})
    assert [t["id"] for t in pendientes.json()] == ["tarea_test_01"]


def test_shopping_list_check(cliente: TestClient, vault_path: Path) -> None:
    (vault_path / "listas" / "compra.md").write_text(
        "# Lista de la compra\n\n"
        "- [ ] Leche entera <!-- item_id:item_leche; cantidad:2.0; "
        "unidad:litros; categoria:lacteos -->\n",
        encoding="utf-8",
    )
    respuesta = cliente.post(
        "/api/shopping-list/check", json={"item_id": "item_leche"}
    )
    assert respuesta.status_code == 200
    assert respuesta.json() == {"item_id": "item_leche", "tachadas": 1}
    texto = (vault_path / "listas" / "compra.md").read_text(encoding="utf-8")
    assert "- [x] Leche entera" in texto

    # Segunda vez: ya no hay línea pendiente que tachar
    respuesta = cliente.post(
        "/api/shopping-list/check", json={"item_id": "item_leche"}
    )
    assert respuesta.status_code == 404


def test_planner_current_get_put(cliente: TestClient) -> None:
    """Sin plan de la semana actual da 404; tras el PUT el GET lo devuelve."""
    from backend.main import _semana_iso_actual

    semana_iso = _semana_iso_actual()
    assert cliente.get("/api/planner/current").status_code == 404

    plan = {
        "semana_iso": semana_iso,
        "fecha_inicio": "2026-08-17",
        "fecha_fin": "2026-08-23",
        "dias": {
            "lunes": {
                "comida": {
                    "receta_id": "recipe_test_01",
                    "plato_libre": None,
                    "raciones": 2,
                    "stock_deducido": False,
                }
            }
        },
        "batch_cooking_programado": [],
    }
    guardado = cliente.put("/api/planner/current", json=plan)
    assert guardado.status_code == 200
    assert guardado.json()["semana_iso"] == semana_iso

    leido = cliente.get("/api/planner/current")
    assert leido.status_code == 200
    assert leido.json()["dias"]["lunes"]["comida"]["receta_id"] == (
        "recipe_test_01"
    )


def test_planner_current_semana_invalida(cliente: TestClient) -> None:
    plan = {
        "semana_iso": "../etc/passwd",
        "fecha_inicio": "2026-08-17",
        "fecha_fin": "2026-08-23",
        "dias": {},
        "batch_cooking_programado": [],
    }
    assert cliente.put("/api/planner/current", json=plan).status_code == 400


def test_finance_summary_404_sin_gastos(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/finance/summary", params={"mes": "2026-08"})
    assert respuesta.status_code == 404


def test_finance_summary_agrega_categorias(
    cliente: TestClient, vault_path: Path
) -> None:
    escribir_md(
        vault_path,
        "inventario/nevera",
        "leche.md",
        {
            "id": "item_leche",
            "nombre": "Leche entera",
            "categoria": "lacteos",
            "ubicacion": "nevera",
            "stock_actual": 2.0,
            "stock_minimo": 1.0,
            "unidad": "litros",
            "lotes": [],
        },
    )
    escribir_md(
        vault_path,
        "gastos",
        "2026-08.md",
        {
            "mes": "2026-08",
            "total_mes": 15.0,
            "tickets": [
                {
                    "comercio": "Mercadona",
                    "fecha": "2026-08-10",
                    "total": 10.0,
                    "items_registrados": ["item_leche"],
                },
                {
                    "comercio": "Farmacia",
                    "fecha": "2026-08-12",
                    "total": 5.0,
                    "items_registrados": ["item_inexistente"],
                },
            ],
        },
    )
    respuesta = cliente.get("/api/finance/summary", params={"mes": "2026-08"})
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["mes"] == "2026-08"
    assert cuerpo["total"] == 15.0
    assert cuerpo["por_categoria"] == [
        {"categoria": "lacteos", "total": 10.0},
        {"categoria": "otros", "total": 5.0},
    ]
