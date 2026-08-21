"""Tests de los routers del planificador y de impresión/NFC (Fase 4c)."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.printer import EscposPrinter
from backend.routers.planner import router as router_planner
from backend.routers.print_nfc import router as router_print_nfc
from backend.vault_manager import VaultManager
from conftest import escribir_md
from test_printer import FakeClienteEscpos

UBICACIONES_JSON = {
    "ubicaciones": [
        {"id": "nevera", "nombre": "Nevera", "tipo": "refrigerado"},
        {"id": "despensa", "nombre": "Despensa", "tipo": "seco"},
    ]
}


def _app_con_vault(vault: VaultManager, printer=None) -> FastAPI:
    """App FastAPI mínima con los routers de Fase 4c y el vault temporal."""
    app = FastAPI()
    app.include_router(router_planner)
    app.include_router(router_print_nfc)
    app.state.vault = vault
    app.state.printer = printer
    return app


def _escribir_receta(vault: VaultManager, receta_id: str = "receta_pasta") -> None:
    escribir_md(
        vault.vault_path,
        "recetas",
        f"{receta_id}.md",
        {
            "id": receta_id,
            "titulo": "Pasta con tomate",
            "categoria": "comida",
            "tiempo_minutos": 20,
            "raciones": 2,
            "ingredientes": [
                {
                    "item_id": "item_pasta",
                    "nombre": "Espaguetis",
                    "cantidad": 200,
                    "unidad": "gramos",
                }
            ],
        },
    )


def _escribir_pasta(vault: VaultManager, stock: float = 500.0) -> None:
    escribir_md(
        vault.vault_path,
        "inventario/despensa",
        "pasta.md",
        {
            "id": "item_pasta",
            "nombre": "Espaguetis",
            "categoria": "despensa_seca",
            "ubicacion": "despensa",
            "stock_actual": stock,
            "stock_minimo": 0.0,
            "unidad": "gramos",
            "lotes": [],
            "auto_lista_compra": False,
        },
    )


@pytest.fixture
def cliente(vault: VaultManager) -> TestClient:
    """TestClient con vault temporal y una impresora fake."""
    fake = FakeClienteEscpos()
    app = _app_con_vault(vault, printer=EscposPrinter(fake))
    cliente = TestClient(app)
    cliente.fake_printer = fake  # acceso al fake desde los tests
    return cliente


# --- Router planner ---------------------------------------------------------------


def test_get_rescue(cliente: TestClient, vault: VaultManager) -> None:
    fecha = (date.today() + timedelta(days=1)).isoformat()
    escribir_md(
        vault.vault_path, "inventario/despensa", "pasta.md",
        {
            "id": "item_pasta", "nombre": "Espaguetis",
            "categoria": "despensa_seca", "ubicacion": "despensa",
            "stock_actual": 5.0, "stock_minimo": 0.0, "unidad": "gramos",
            "fecha_caducidad_proxima": fecha, "lotes": [],
        },
    )
    _escribir_receta(vault)

    respuesta = cliente.get("/api/planner/rescue", params={"dias": 4})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert len(cuerpo) == 1
    assert cuerpo[0]["receta"]["id"] == "receta_pasta"


def test_post_batch_cooking_ok(cliente: TestClient, vault: VaultManager) -> None:
    _escribir_pasta(vault)
    _escribir_receta(vault)

    respuesta = cliente.post(
        "/api/planner/batch-cooking", json={"receta_ids": ["receta_pasta"]}
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["destino"] == "congelador"
    assert len(cuerpo["tuppers"]) == 1
    assert cuerpo["ingredientes"][0]["consumido"] is True


def test_post_batch_cooking_receta_inexistente(cliente: TestClient) -> None:
    respuesta = cliente.post(
        "/api/planner/batch-cooking", json={"receta_ids": ["receta_fantasma"]}
    )
    assert respuesta.status_code == 404


def test_post_batch_cooking_destino_invalido(
    cliente: TestClient, vault: VaultManager
) -> None:
    _escribir_receta(vault)
    respuesta = cliente.post(
        "/api/planner/batch-cooking",
        json={"receta_ids": ["receta_pasta"], "destino": "luna"},
    )
    assert respuesta.status_code == 400


def test_post_evento_ok(cliente: TestClient, vault: VaultManager) -> None:
    _escribir_pasta(vault, stock=100.0)
    _escribir_receta(vault)

    respuesta = cliente.post(
        "/api/planner/evento",
        json={"receta_ids": ["receta_pasta"], "invitados": 4},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["invitados"] == 4
    assert cuerpo["faltantes"][0]["faltante"] == pytest.approx(300.0)
    assert cuerpo["faltantes"][0]["anadido_a_lista"] is True


def test_post_evento_receta_inexistente(cliente: TestClient) -> None:
    respuesta = cliente.post(
        "/api/planner/evento",
        json={"receta_ids": ["receta_fantasma"], "invitados": 4},
    )
    assert respuesta.status_code == 404


def test_post_evento_invitados_invalidos(cliente: TestClient) -> None:
    respuesta = cliente.post(
        "/api/planner/evento",
        json={"receta_ids": ["receta_pasta"], "invitados": 0},
    )
    assert respuesta.status_code == 422  # validación Pydantic del body


# --- Router print / NFC --------------------------------------------------------------


def test_print_receipt_list(cliente: TestClient, vault: VaultManager) -> None:
    (vault.vault_path / "listas" / "compra.md").write_text(
        "# Lista de la compra\n\n"
        "- [ ] Leche entera <!-- item_id:item_leche; cantidad:2.0;"
        " unidad:litros; categoria:lacteos -->\n"
        "- [x] Pan <!-- item_id:item_pan; cantidad:1.0;"
        " unidad:unidades; categoria:despensa_seca -->\n",
        encoding="utf-8",
    )

    respuesta = cliente.post("/api/print/receipt-list")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"impreso": True, "lineas": 1}
    ticket = "".join(cliente.fake_printer.textos)
    assert "Leche entera" in ticket
    assert "Pan" not in ticket  # los comprados no se imprimen


def test_print_receipt_list_sin_impresora(
    vault: VaultManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRINTER_HOST", raising=False)
    app = _app_con_vault(vault, printer=None)
    respuesta = TestClient(app).post("/api/print/receipt-list")
    assert respuesta.status_code == 503


def test_print_receipt_list_error_impresora(vault: VaultManager) -> None:
    app = _app_con_vault(
        vault, printer=EscposPrinter(FakeClienteEscpos(fallar=True))
    )
    respuesta = TestClient(app).post("/api/print/receipt-list")
    assert respuesta.status_code == 502


def test_print_label_tupper(cliente: TestClient) -> None:
    respuesta = cliente.post(
        "/api/print/label-tupper",
        json={
            "nombre": "Pasta con tomate",
            "fecha_congelacion": "2026-08-21",
            "qr_data": "homevault://item/tupper_1",
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["impreso"] is True
    assert cliente.fake_printer.qrs == ["homevault://item/tupper_1"]


def test_location_devuelve_items(cliente: TestClient, vault: VaultManager) -> None:
    (vault.vault_path / "config" / "ubicaciones.json").write_text(
        json.dumps(UBICACIONES_JSON), encoding="utf-8"
    )
    _escribir_pasta(vault)

    respuesta = cliente.get("/location/despensa")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["slug"] == "despensa"
    assert cuerpo["nombre"] == "Despensa"
    assert [i["id"] for i in cuerpo["items"]] == ["item_pasta"]


def test_location_slug_desconocido(cliente: TestClient, vault: VaultManager) -> None:
    (vault.vault_path / "config" / "ubicaciones.json").write_text(
        json.dumps(UBICACIONES_JSON), encoding="utf-8"
    )
    respuesta = cliente.get("/location/azotea")
    assert respuesta.status_code == 404


def test_location_sin_json(cliente: TestClient) -> None:
    respuesta = cliente.get("/location/nevera")
    assert respuesta.status_code == 404
