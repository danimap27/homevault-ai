"""Tests de "qué recetas puedo hacer", cook transaccional y plan assign."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import Consumible, Ingrediente, Receta
from backend.planner import InsufficientStockError, Planner
from backend.vault_manager import VaultManager


@pytest.fixture
def planner(vault: VaultManager) -> Planner:
    """Planner sobre el vault temporal."""
    return Planner(vault)


@pytest.fixture
def cliente(vault_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient con vault temporal para tests de endpoints."""
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    with TestClient(app) as cliente:
        yield cliente


async def _crear_item(
    vault: VaultManager,
    item_id: str,
    nombre: str,
    stock: float,
    ubicacion: str = "despensa",
    unidad: str = "unidades",
) -> Consumible:
    """Helper para crear un ítem de prueba."""
    item = Consumible(
        id=item_id,
        nombre=nombre,
        categoria="despensa_seca",
        ubicacion=ubicacion,
        stock_actual=stock,
        stock_minimo=0.0,
        unidad=unidad,
    )
    return await vault.create_item(item)


async def _crear_receta(
    vault: VaultManager,
    receta_id: str,
    titulo: str,
    ingredientes: list[tuple[str | None, str, float, str]],
    raciones: int = 2,
) -> Receta:
    """Helper para crear una receta de prueba."""
    ings = [
        Ingrediente(item_id=iid, nombre=nom, cantidad=cant, unidad=unid)
        for iid, nom, cant, unid in ingredientes
    ]
    receta = Receta(
        id=receta_id,
        titulo=titulo,
        categoria="comida",
        tiempo_minutos=30,
        raciones=raciones,
        ingredientes=ings,
    )
    return await vault.create_receta(receta)


async def test_possible_recipes_orden_por_score(
    vault: VaultManager, planner: Planner
) -> None:
    """Las recetas se ordenan por score descendente y faltante ascendente."""
    await _crear_item(vault, "item_huevos", "Huevos", stock=6.0)
    await _crear_item(vault, "item_pan", "Pan", stock=4.0)
    await _crear_item(vault, "item_leche", "Leche", stock=0.0)

    await _crear_receta(
        vault,
        "recipe_tortilla",
        "Tortilla",
        [("item_huevos", "Huevos", 3.0, "unidades")],
    )
    await _crear_receta(
        vault,
        "recipe_revuelto",
        "Revuelto",
        [
            ("item_huevos", "Huevos", 3.0, "unidades"),
            ("item_leche", "Leche", 1.0, "litros"),
        ],
    )
    await _crear_receta(
        vault,
        "recipe_tostada",
        "Tostada",
        [("item_pan", "Pan", 2.0, "unidades")],
    )

    posibles = await planner.possible_recipes()
    ids = [p.receta.id for p in posibles]

    # Tostada y tortilla tienen score 1.0; revuelto 0.5
    # Empate por faltante ascendente; ambas completas tienen 0 faltantes,
    # así que se mantiene el orden estable de list_recipes (alfabético).
    assert ids == ["recipe_tortilla", "recipe_tostada", "recipe_revuelto"]
    assert posibles[0].score == 1.0
    assert posibles[0].ingredientes_satisfechos == 1
    assert posibles[2].score == 0.5


async def test_possible_recipes_sin_ingredientes_vinculados_score_uno(
    vault: VaultManager, planner: Planner
) -> None:
    """Una receta sin ingredientes vinculados obtiene score 1.0."""
    await _crear_receta(
        vault,
        "recipe_libre",
        "Plato libre",
        [(None, "Sal", 1.0, "unidades")],
    )

    posibles = await planner.possible_recipes()
    assert len(posibles) == 1
    assert posibles[0].score == 1.0
    assert posibles[0].faltantes_para_compra == []


async def test_cook_recipe_exitoso_descuenta_stock(
    vault: VaultManager, planner: Planner
) -> None:
    """cook_recipe consume cada ingrediente proporcionalmente."""
    await _crear_item(vault, "item_pasta", "Pasta", stock=500.0, unidad="gramos")
    await _crear_item(vault, "item_tomate", "Tomate", stock=3.0)
    await _crear_receta(
        vault,
        "recipe_pasta_tomate",
        "Pasta con tomate",
        [
            ("item_pasta", "Pasta", 200.0, "gramos"),
            ("item_tomate", "Tomate", 1.0, "unidades"),
        ],
        raciones=2,
    )

    resultado = await planner.cook_recipe("recipe_pasta_tomate", raciones=4)

    assert len(resultado.consumidos) == 2
    assert resultado.faltantes == []
    pasta = await vault.get_item("item_pasta")
    tomate = await vault.get_item("item_tomate")
    assert pasta is not None and pasta.stock_actual == pytest.approx(100.0)
    assert tomate is not None and tomate.stock_actual == pytest.approx(1.0)


async def test_cook_recipe_transaccional_no_consume_si_falta(
    vault: VaultManager, planner: Planner
) -> None:
    """Si falta un ingrediente no se consume nada del inventario."""
    await _crear_item(vault, "item_pasta", "Pasta", stock=500.0, unidad="gramos")
    await _crear_item(vault, "item_tomate", "Tomate", stock=0.0)
    await _crear_receta(
        vault,
        "recipe_pasta_tomate",
        "Pasta con tomate",
        [
            ("item_pasta", "Pasta", 200.0, "gramos"),
            ("item_tomate", "Tomate", 1.0, "unidades"),
        ],
        raciones=2,
    )

    with pytest.raises(InsufficientStockError) as exc_info:
        await planner.cook_recipe("recipe_pasta_tomate", raciones=2)

    faltantes = exc_info.value.faltantes
    assert len(faltantes) == 1
    assert faltantes[0].item_id == "item_tomate"

    pasta = await vault.get_item("item_pasta")
    assert pasta is not None and pasta.stock_actual == pytest.approx(500.0)


def test_assign_recipe_endpoint_crea_plan_y_anade_faltantes(
    cliente: TestClient, vault_path: Path
) -> None:
    """POST /api/planner/assign guarda el plan y vuelca faltantes a compra."""
    from backend.vault_manager import VaultManager

    vault = VaultManager(vault_path)

    # Pasta con stock insuficiente para 4 raciones (necesita 400g)
    # Usamos run_sync? No: llamadas async deben ejecutarse con asyncio.run
    import asyncio

    async def setup() -> None:
        item = Consumible(
            id="item_pasta",
            nombre="Pasta",
            categoria="despensa_seca",
            ubicacion="despensa",
            stock_actual=100.0,
            stock_minimo=0.0,
            unidad="gramos",
        )
        await vault.create_item(item)
        receta = Receta(
            id="recipe_pasta",
            titulo="Pasta",
            categoria="comida",
            tiempo_minutos=20,
            raciones=2,
            ingredientes=[
                Ingrediente(
                    item_id="item_pasta",
                    nombre="Pasta",
                    cantidad=200.0,
                    unidad="gramos",
                )
            ],
        )
        await vault.create_receta(receta)

    asyncio.run(setup())

    respuesta = cliente.post(
        "/api/planner/assign",
        json={
            "semana_iso": "2026-W40",
            "dia": "lunes",
            "toma": "comida",
            "receta_id": "recipe_pasta",
            "raciones": 4,
        },
    )

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["plan"]["semana_iso"] == "2026-W40"
    assert datos["plan"]["dias"]["lunes"]["comida"]["receta_id"] == "recipe_pasta"
    assert datos["plan"]["dias"]["lunes"]["comida"]["raciones"] == 4
    assert len(datos["faltantes_anadidos"]) == 1
    assert datos["faltantes_anadidos"][0]["item_id"] == "item_pasta"
    assert datos["faltantes_anadidos"][0]["cantidad"] == pytest.approx(300.0)

    ruta_plan = vault_path / "planificador" / "2026-W40.md"
    assert ruta_plan.exists()
