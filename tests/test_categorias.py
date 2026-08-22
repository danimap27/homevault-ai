"""Tests del catálogo dinámico de categorías y su integración con inventario."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.categorias import CategoriaManager
from backend.main import app


@pytest.fixture
def cliente(vault_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient de la app completa con un vault temporal."""
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    with TestClient(app) as cliente:
        yield cliente


# --- Manager -----------------------------------------------------------------


def test_categorias_por_defecto_se_cargan(vault_path: str) -> None:
    """Al inicializar el manager se crean las 6 categorías originales."""
    manager = CategoriaManager(vault_path)

    ids = {c.id for c in manager.listar()}

    assert ids == {
        "lacteos",
        "congelados",
        "despensa_seca",
        "limpieza",
        "recambios_hogar",
        "botiquin",
    }


def test_manager_crear_y_borrar(vault_path: str) -> None:
    """CRUD básico del CategoriaManager."""
    manager = CategoriaManager(vault_path)

    creada = manager.crear(
        nombre="Bebidas",
        color="#123456",
        icono="🥤",
        ubicacion_default="nevera",
        orden=10,
    )
    assert creada.id == "bebidas"
    assert creada.orden == 10

    assert manager.obtener("bebidas") is not None
    assert manager.existe("bebidas") is True

    manager.actualizar("bebidas", nombre="Bebidas y refrescos")
    assert manager.obtener("bebidas").nombre == "Bebidas y refrescos"

    assert manager.borrar("bebidas") is True
    assert manager.existe("bebidas") is False
    assert manager.borrar("bebidas") is False


def test_manager_color_invalido_lanza_error(vault_path: str) -> None:
    """El color debe ser un HEX de 6 dígitos."""
    manager = CategoriaManager(vault_path)

    with pytest.raises(ValueError, match="HEX"):
        manager.crear(nombre="Mala", color="rojo")


# --- Endpoints ---------------------------------------------------------------


def test_api_crud_categorias(cliente: TestClient) -> None:
    """POST/GET/PUT/DELETE de /api/categories."""
    crear = cliente.post(
        "/api/categories",
        json={
            "nombre": "Bebidas",
            "color": "#123456",
            "icono": "🥤",
            "ubicacion_default": "nevera",
            "orden": 10,
        },
    )
    assert crear.status_code == 201
    assert crear.json()["id"] == "bebidas"

    lista = cliente.get("/api/categories").json()
    assert any(c["id"] == "bebidas" for c in lista)

    actualizar = cliente.put(
        "/api/categories/bebidas",
        json={"nombre": "Bebidas y refrescos"},
    )
    assert actualizar.status_code == 200
    assert actualizar.json()["nombre"] == "Bebidas y refrescos"

    borrar = cliente.delete("/api/categories/bebidas")
    assert borrar.status_code == 200
    assert borrar.json()["eliminada"] is True


def test_api_no_borrar_categoria_en_uso(cliente: TestClient) -> None:
    """DELETE devuelve 409 con los ids de los ítems afectados."""
    item = {
        "id": "item_leche_test",
        "nombre": "Leche de prueba",
        "categoria": "lacteos",
        "ubicacion": "nevera",
        "stock_actual": 1.0,
        "stock_minimo": 0.0,
        "unidad": "litros",
    }
    assert cliente.post("/api/inventory", json=item).status_code == 201

    respuesta = cliente.delete("/api/categories/lacteos")
    assert respuesta.status_code == 409
    detalle = respuesta.json()["detail"]
    assert detalle["categoria"] == "lacteos"
    assert "item_leche_test" in detalle["items_afectados"]


def test_api_borrar_categoria_reasignando_items(cliente: TestClient) -> None:
    """`reemplazar_por` mueve los ítems antes de eliminar la categoría."""
    item = {
        "id": "item_leche_test",
        "nombre": "Leche de prueba",
        "categoria": "lacteos",
        "ubicacion": "nevera",
        "stock_actual": 1.0,
        "stock_minimo": 0.0,
        "unidad": "litros",
    }
    assert cliente.post("/api/inventory", json=item).status_code == 201

    respuesta = cliente.delete(
        "/api/categories/lacteos?reemplazar_por=despensa_seca"
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["items_afectados"] == ["item_leche_test"]

    items = cliente.get("/api/inventory").json()
    item_actualizado = next(i for i in items if i["id"] == "item_leche_test")
    assert item_actualizado["categoria"] == "despensa_seca"
    assert not any(
        c["id"] == "lacteos"
        for c in cliente.get("/api/categories").json()
    )


def test_api_crear_item_con_categoria_personalizada(cliente: TestClient) -> None:
    """Se puede crear un ítem con una categoría añadida dinámicamente."""
    assert (
        cliente.post(
            "/api/categories",
            json={"nombre": "Especias", "color": "#a855f7", "icono": "🌶️"},
        ).status_code
        == 201
    )

    item = {
        "id": "item_curcuma",
        "nombre": "Cúrcuma",
        "categoria": "especias",
        "ubicacion": "despensa",
        "stock_actual": 50.0,
        "stock_minimo": 10.0,
        "unidad": "gramos",
    }
    respuesta = cliente.post("/api/inventory", json=item)
    assert respuesta.status_code == 201
    assert respuesta.json()["categoria"] == "especias"


def test_api_reasignar_categoria_de_item(cliente: TestClient) -> None:
    """PUT /api/inventory/{id} permite cambiar la categoría validando contra el catálogo."""
    item = {
        "id": "item_yogur_test",
        "nombre": "Yogur",
        "categoria": "lacteos",
        "ubicacion": "nevera",
        "stock_actual": 4.0,
        "stock_minimo": 1.0,
        "unidad": "unidades",
    }
    assert cliente.post("/api/inventory", json=item).status_code == 201

    respuesta = cliente.put(
        "/api/inventory/item_yogur_test",
        json={"categoria": "despensa_seca"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["categoria"] == "despensa_seca"


def test_api_put_item_usa_move_item_para_ubicacion(cliente: TestClient) -> None:
    """PUT /api/inventory/{id} traslada el archivo si cambia la ubicación."""
    item = {
        "id": "item_mermelada_test",
        "nombre": "Mermelada",
        "categoria": "despensa_seca",
        "ubicacion": "despensa",
        "stock_actual": 1.0,
        "stock_minimo": 0.0,
        "unidad": "gramos",
    }
    assert cliente.post("/api/inventory", json=item).status_code == 201

    respuesta = cliente.put(
        "/api/inventory/item_mermelada_test",
        json={"ubicacion": "nevera"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["ubicacion"] == "nevera"


def test_api_categoria_invalida_en_item_400(cliente: TestClient) -> None:
    """Crear o mover un ítem a una categoría inexistente devuelve 400."""
    item = {
        "id": "item_malo",
        "nombre": "Malo",
        "categoria": "no_existe",
        "ubicacion": "despensa",
        "stock_actual": 1.0,
        "stock_minimo": 0.0,
        "unidad": "unidades",
    }
    respuesta = cliente.post("/api/inventory", json=item)
    assert respuesta.status_code == 400
    assert "Categoría no válida" in respuesta.json()["detail"]
