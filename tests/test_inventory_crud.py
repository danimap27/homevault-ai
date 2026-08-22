"""Tests del CRUD de ítems de inventario."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.models import Consumible
from backend.vault_manager import VaultManager


async def test_create_item_crea_archivo_en_ubicacion(vault: VaultManager) -> None:
    """create_item persiste el ítem en inventario/<ubicacion>/<id>.md."""
    item = Consumible(
        id="item_huevos_01",
        nombre="Huevos camperos",
        categoria="lacteos",
        ubicacion="nevera",
        stock_actual=12.0,
        stock_minimo=3.0,
        unidad="unidades",
    )

    resultado = await vault.create_item(item)

    assert resultado.id == "item_huevos_01"
    ruta = vault.vault_path / "inventario" / "nevera" / "item_huevos_01.md"
    assert ruta.exists()
    leido = await vault.get_item("item_huevos_01")
    assert leido is not None
    assert leido.nombre == "Huevos camperos"
    assert leido.ubicacion == "nevera"


async def test_create_item_rechaza_duplicado(vault: VaultManager) -> None:
    """No se pueden crear dos ítems con el mismo id en la misma ubicación."""
    item = Consumible(
        id="item_huevos_01",
        nombre="Huevos",
        categoria="lacteos",
        ubicacion="nevera",
        unidad="unidades",
    )
    await vault.create_item(item)

    with pytest.raises(FileExistsError):
        await vault.create_item(item)


async def test_update_item_aplica_campos_editables(
    vault: VaultManager,
) -> None:
    """update_item modifica los campos permitidos y preserva el cuerpo."""
    item = Consumible(
        id="item_leche_01",
        nombre="Leche entera",
        categoria="lacteos",
        ubicacion="nevera",
        stock_actual=2.0,
        stock_minimo=1.0,
        unidad="litros",
    )
    await vault.create_item(item)
    ruta = vault.vault_path / "inventario" / "nevera" / "item_leche_01.md"
    cuerpo_original = ruta.read_text(encoding="utf-8")

    actualizado = await vault.update_item(
        "item_leche_01",
        {
            "nombre": "Leche semi",
            "stock_minimo": 2.0,
            "auto_lista_compra": True,
            "tags": ["desayuno"],
        },
    )

    assert actualizado.nombre == "Leche semi"
    assert actualizado.stock_minimo == 2.0
    assert actualizado.auto_lista_compra is True
    assert actualizado.tags == ["desayuno"]
    # stock_actual no cambia
    assert actualizado.stock_actual == 2.0
    # cuerpo libre preservado (después del frontmatter)
    assert ruta.read_text(encoding="utf-8").split("---\n\n", 1)[1] == (
        cuerpo_original.split("---\n\n", 1)[1]
    )


async def test_update_item_no_permite_id(vault: VaultManager) -> None:
    """update_item rechaza cambios de id."""
    item = Consumible(
        id="item_leche_01",
        nombre="Leche",
        categoria="lacteos",
        ubicacion="nevera",
        unidad="litros",
    )
    await vault.create_item(item)

    with pytest.raises(ValueError, match="id"):
        await vault.update_item("item_leche_01", {"id": "otro"})


async def test_update_item_no_permite_stock_actual(
    vault: VaultManager,
) -> None:
    """update_item rechaza cambios directos de stock_actual."""
    item = Consumible(
        id="item_leche_01",
        nombre="Leche",
        categoria="lacteos",
        ubicacion="nevera",
        unidad="litros",
    )
    await vault.create_item(item)

    with pytest.raises(ValueError, match="stock_actual"):
        await vault.update_item("item_leche_01", {"stock_actual": 99.0})


async def test_update_item_mueve_archivo_si_cambia_ubicacion(
    vault: VaultManager,
) -> None:
    """Si update_item cambia la ubicación, el archivo se traslada."""
    item = Consumible(
        id="item_mermelada_01",
        nombre="Mermelada",
        categoria="despensa_seca",
        ubicacion="nevera",
        unidad="gramos",
    )
    await vault.create_item(item)
    ruta_origen = vault.vault_path / "inventario" / "nevera" / "item_mermelada_01.md"

    actualizado = await vault.update_item(
        "item_mermelada_01", {"ubicacion": "despensa"}
    )

    assert actualizado.ubicacion == "despensa"
    assert not ruta_origen.exists()
    ruta_destino = (
        vault.vault_path / "inventario" / "despensa" / "item_mermelada_01.md"
    )
    assert ruta_destino.exists()
    leido = await vault.get_item("item_mermelada_01")
    assert leido is not None and leido.ubicacion == "despensa"


async def test_delete_item_borra_archivo(vault: VaultManager) -> None:
    """delete_item elimina el archivo .md del ítem."""
    item = Consumible(
        id="item_borrar_01",
        nombre="Papel de cocina",
        categoria="limpieza",
        ubicacion="trastero",
        unidad="unidades",
    )
    await vault.create_item(item)

    borrado = await vault.delete_item("item_borrar_01")

    assert borrado is True
    assert not (
        vault.vault_path / "inventario" / "trastero" / "item_borrar_01.md"
    ).exists()
    assert await vault.get_item("item_borrar_01") is None


async def test_delete_item_inexistente_devuelve_falso(
    vault: VaultManager,
) -> None:
    """delete_item devuelve False si el ítem no existe."""
    assert await vault.delete_item("item_fantasma") is False


async def test_move_item_cambia_categoria_y_ubicacion(
    vault: VaultManager,
) -> None:
    """move_item traslada el archivo y actualiza categoría y ubicación."""
    item = Consumible(
        id="item_pasta_01",
        nombre="Espaguetis",
        categoria="despensa_seca",
        ubicacion="despensa",
        unidad="gramos",
    )
    await vault.create_item(item)

    movido = await vault.move_item(
        "item_pasta_01",
        nueva_categoria="despensa_seca",
        nueva_ubicacion="nevera",
    )

    assert movido.ubicacion == "nevera"
    assert not (
        vault.vault_path / "inventario" / "despensa" / "item_pasta_01.md"
    ).exists()
    assert (
        vault.vault_path / "inventario" / "nevera" / "item_pasta_01.md"
    ).exists()
