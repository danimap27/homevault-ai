"""Tests del CRUD de recetas."""

from __future__ import annotations

import pytest

from backend.models import Ingrediente, Receta
from backend.vault_manager import VaultManager


async def test_create_receta_crea_archivo(vault: VaultManager) -> None:
    """create_receta persiste la receta en recetas/<id>.md."""
    receta = Receta(
        id="recipe_tortilla",
        titulo="Tortilla de patatas",
        categoria="comida",
        tiempo_minutos=40,
        raciones=4,
        ingredientes=[
            Ingrediente(
                item_id=None,
                nombre="Huevos",
                cantidad=6.0,
                unidad="unidades",
            ),
        ],
    )

    resultado = await vault.create_receta(receta)

    assert resultado.id == "recipe_tortilla"
    ruta = vault.vault_path / "recetas" / "recipe_tortilla.md"
    assert ruta.exists()
    leida = await vault.get_receta("recipe_tortilla")
    assert leida is not None
    assert leida.titulo == "Tortilla de patatas"
    assert len(leida.ingredientes) == 1


async def test_create_receta_rechaza_duplicado(vault: VaultManager) -> None:
    """No se pueden crear dos recetas con el mismo id."""
    receta = Receta(
        id="recipe_tortilla",
        titulo="Tortilla",
        categoria="comida",
        tiempo_minutos=30,
        raciones=2,
    )
    await vault.create_receta(receta)

    with pytest.raises(FileExistsError):
        await vault.create_receta(receta)


async def test_get_receta_inexistente(vault: VaultManager) -> None:
    """get_receta devuelve None si no existe."""
    assert await vault.get_receta("recipe_fantasma") is None


async def test_update_receta_aplica_campos_editables(
    vault: VaultManager,
) -> None:
    """update_receta modifica campos editables incluyendo ingredientes."""
    receta = Receta(
        id="recipe_gazpacho",
        titulo="Gazpacho",
        categoria="comida",
        tiempo_minutos=15,
        raciones=4,
        ingredientes=[
            Ingrediente(
                item_id=None,
                nombre="Tomate",
                cantidad=1.0,
                unidad="kg",
            ),
        ],
    )
    await vault.create_receta(receta)
    ruta = vault.vault_path / "recetas" / "recipe_gazpacho.md"
    cuerpo_original = ruta.read_text(encoding="utf-8")

    actualizada = await vault.update_receta(
        "recipe_gazpacho",
        {
            "titulo": "Gazpacho andaluz",
            "tiempo_minutos": 20,
            "ingredientes": [
                {
                    "item_id": None,
                    "nombre": "Tomate",
                    "cantidad": 1.5,
                    "unidad": "kg",
                },
                {
                    "item_id": None,
                    "nombre": "Pepino",
                    "cantidad": 0.5,
                    "unidad": "kg",
                },
            ],
        },
    )

    assert actualizada.titulo == "Gazpacho andaluz"
    assert actualizada.tiempo_minutos == 20
    assert len(actualizada.ingredientes) == 2
    assert actualizada.ingredientes[0].cantidad == 1.5
    # El cuerpo Markdown libre se conserva
    assert ruta.read_text(encoding="utf-8").split("---\n\n", 1)[1] == (
        cuerpo_original.split("---\n\n", 1)[1]
    )


async def test_update_receta_no_permite_id(vault: VaultManager) -> None:
    """update_receta rechaza cambios de id."""
    receta = Receta(
        id="recipe_gazpacho",
        titulo="Gazpacho",
        categoria="comida",
        tiempo_minutos=15,
        raciones=4,
    )
    await vault.create_receta(receta)

    with pytest.raises(ValueError, match="id"):
        await vault.update_receta("recipe_gazpacho", {"id": "otro"})


async def test_delete_receta_borra_archivo(vault: VaultManager) -> None:
    """delete_receta elimina el archivo .md de la receta."""
    receta = Receta(
        id="recipe_borrar",
        titulo="Borrable",
        categoria="cena",
        tiempo_minutos=10,
        raciones=1,
    )
    await vault.create_receta(receta)

    borrada = await vault.delete_receta("recipe_borrar")

    assert borrada is True
    assert not (vault.vault_path / "recetas" / "recipe_borrar.md").exists()
    assert await vault.get_receta("recipe_borrar") is None


async def test_delete_receta_inexistente_devuelve_falso(
    vault: VaultManager,
) -> None:
    """delete_receta devuelve False si la receta no existe."""
    assert await vault.delete_receta("recipe_fantasma") is False
