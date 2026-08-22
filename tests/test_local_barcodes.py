"""Tests de la base de datos local de códigos de barras."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.local_barcodes import LocalBarcode, LocalBarcodeManager
from backend.main import app
from backend.routers.barcode import router as barcode_router
from backend.vault_manager import VaultManager
from fastapi import FastAPI


def _manager(vault_path: Path) -> LocalBarcodeManager:
    """Helper para instanciar el manager con un vault temporal."""
    return LocalBarcodeManager(vault_path)


def test_poblacion_inicial_tiene_productos_comunes(vault_path: Path) -> None:
    """La base local se inicializa con ~50 productos españoles."""
    manager = _manager(vault_path)

    barcodes = manager.listar()

    assert len(barcodes) >= 50
    # Todos los EANs empiezan por 84 y tienen 13 dígitos
    for b in barcodes:
        assert b.ean.isdigit()
        assert len(b.ean) == 13
        assert b.ean.startswith("84")
    # Algunas categorías representadas
    categorias = {b.categoria for b in barcodes}
    assert "lacteos" in categorias
    assert "despensa_seca" in categorias
    assert "limpieza" in categorias


def test_obtener_por_ean(vault_path: Path) -> None:
    """obtener devuelve el producto local o None."""
    manager = _manager(vault_path)
    primero = manager.listar()[0]

    encontrado = manager.obtener(primero.ean)
    assert encontrado is not None
    assert encontrado.ean == primero.ean

    assert manager.obtener("8400000009999") is None


def test_crear_y_borrar(vault_path: Path) -> None:
    """CRUD básico de códigos de barras locales."""
    manager = _manager(vault_path)
    nuevo = LocalBarcode(
        ean="8400000009999",
        nombre="Producto de prueba",
        categoria="despensa_seca",
        ubicacion="despensa",
        unidad="unidades",
        supermercado="Test",
        precio_unitario_estimado=1.99,
        tags=["test"],
    )

    creado = manager.crear(nuevo)
    assert creado.ean == nuevo.ean

    with pytest.raises(ValueError):
        manager.crear(nuevo)  # EAN duplicado

    actualizado = manager.actualizar(nuevo.ean, precio_unitario_estimado=2.50)
    assert actualizado.precio_unitario_estimado == 2.50

    assert manager.borrar(nuevo.ean) is True
    assert manager.obtener(nuevo.ean) is None


def test_ean_invalido_lanza_error(vault_path: Path) -> None:
    """obtener/crear con EAN mal formado lanzan ValueError."""
    manager = _manager(vault_path)
    with pytest.raises(ValueError):
        manager.obtener("123")


@pytest.fixture
def cliente_barcode(vault: VaultManager) -> TestClient:
    """TestClient del router barcode con local barcodes disponibles."""
    app_test = FastAPI()
    app_test.state.vault = vault
    app_test.state.off_client = None  # fuerza a que resuelva local o 503
    app_test.include_router(barcode_router)
    return TestClient(app_test)


def test_resolucion_local_barcode_crea_item(vault: VaultManager, cliente_barcode: TestClient) -> None:
    """GET /api/barcode/{ean} resuelve desde local barcodes si existe."""
    manager = LocalBarcodeManager(vault.vault_path)
    barcode = manager.listar()[0]

    respuesta = cliente_barcode.get(f"/api/barcode/{barcode.ean}")

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["origen"] == "local"
    assert datos["creado"] is True
    assert datos["item"]["ean_barcode"] == barcode.ean
    assert datos["item"]["nombre"] == barcode.nombre

    # Segunda consulta resuelve ya desde el vault
    segunda = cliente_barcode.get(f"/api/barcode/{barcode.ean}")
    assert segunda.json()["origen"] == "vault"


@pytest.fixture
def cliente(vault_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient de la app completa con el vault temporal."""
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    with TestClient(app) as cliente:
        yield cliente


def test_api_local_barcodes_crud(cliente: TestClient) -> None:
    """GET/POST/PUT/DELETE de /api/local-barcodes."""
    lista = cliente.get("/api/local-barcodes").json()
    assert len(lista) >= 50

    nuevo = {
        "ean": "8400000009998",
        "nombre": "Test product",
        "categoria": "despensa_seca",
        "ubicacion": "despensa",
        "unidad": "unidades",
        "supermercado": "Test",
        "precio_unitario_estimado": 1.50,
        "tags": ["test"],
    }
    creado = cliente.post("/api/local-barcodes", json=nuevo)
    assert creado.status_code == 201

    actualizado = cliente.put(
        "/api/local-barcodes/8400000009998",
        json={**nuevo, "precio_unitario_estimado": 2.00},
    )
    assert actualizado.status_code == 200
    assert actualizado.json()["precio_unitario_estimado"] == 2.00

    assert cliente.get("/api/local-barcodes/8400000009998").status_code == 200

    borrado = cliente.delete("/api/local-barcodes/8400000009998")
    assert borrado.status_code == 204
    assert cliente.get("/api/local-barcodes/8400000009998").status_code == 404
