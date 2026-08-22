"""Tests de gestión de la lista de la compra.

Cubre los métodos públicos del VaultManager y los endpoints REST de
``/api/shopping-list`` para borrar y editar entradas pendientes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.vault_manager import VaultManager


def _escribir_lista(vault_path, contenido: str) -> None:
    """Helper para escribir listas/compra.md en tests síncronos."""
    (vault_path / "listas" / "compra.md").write_text(contenido, encoding="utf-8")


async def test_remove_shopping_list_entry_borra_pendientes_por_item_id(
    vault: VaultManager,
) -> None:
    """remove_shopping_list_entry borra solo líneas pendientes del item_id."""
    ruta = vault.vault_path / "listas" / "compra.md"
    ruta.write_text(
        "# Lista de la compra\n\n"
        "- [ ] Leche <!-- item_id:item_leche; cantidad:2.0; unidad:litros; categoria:lacteos -->\n"
        "- [x] Pan <!-- item_id:item_pan; cantidad:1.0; unidad:unidades; categoria:despensa_seca -->\n"
        "- [ ] Yogur <!-- item_id:item_yogur; cantidad:4.0; unidad:unidades; categoria:lacteos -->\n",
        encoding="utf-8",
    )

    borradas = await vault.remove_shopping_list_entry("item_leche")

    assert borradas == 1
    texto = ruta.read_text(encoding="utf-8")
    assert "item_leche" not in texto
    assert "item_pan" in texto  # línea tachada, no se borra
    assert "item_yogur" in texto


async def test_remove_shopping_list_entry_borra_tambien_tachadas(
    vault: VaultManager,
) -> None:
    """remove_shopping_list_entry elimina líneas independientemente del estado."""
    ruta = vault.vault_path / "listas" / "compra.md"
    ruta.write_text(
        "# Lista de la compra\n\n"
        "- [x] Leche <!-- item_id:item_leche; cantidad:2.0; unidad:litros; categoria:lacteos -->\n",
        encoding="utf-8",
    )

    borradas = await vault.remove_shopping_list_entry("item_leche")

    assert borradas == 1
    assert "item_leche" not in ruta.read_text(encoding="utf-8")


async def test_update_shopping_list_entry_edita_campos(
    vault: VaultManager,
) -> None:
    """update_shopping_list_entry modifica cantidad, unidad y categoría."""
    ruta = vault.vault_path / "listas" / "compra.md"
    ruta.write_text(
        "# Lista de la compra\n\n"
        "- [ ] Leche <!-- item_id:item_leche; cantidad:2.0; unidad:litros; categoria:lacteos -->\n",
        encoding="utf-8",
    )

    editadas = await vault.update_shopping_list_entry(
        "item_leche", cantidad=3.0, unidad="botellas"
    )

    assert editadas == 1
    texto = ruta.read_text(encoding="utf-8")
    assert "cantidad:3.0" in texto
    assert "unidad:botellas" in texto
    assert "categoria:lacteos" in texto  # no cambió


async def test_update_shopping_list_entry_no_crea_si_no_existe(
    vault: VaultManager,
) -> None:
    """update_shopping_list_entry no crea líneas si no hay coincidencia."""
    ruta = vault.vault_path / "listas" / "compra.md"
    original = "# Lista de la compra\n\n"
    ruta.write_text(original, encoding="utf-8")

    editadas = await vault.update_shopping_list_entry(
        "item_inexistente", cantidad=1.0
    )

    assert editadas == 0
    assert ruta.read_text(encoding="utf-8") == original


@pytest.fixture
def cliente(vault_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient de la app completa con el vault temporal."""
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    with TestClient(app) as cliente:
        yield cliente


def test_api_borrar_entrada_lista(cliente: TestClient, vault_path) -> None:
    """DELETE /api/shopping-list/{item_id} borra líneas pendientes."""
    _escribir_lista(
        vault_path,
        "# Lista de la compra\n\n"
        "- [ ] Leche <!-- item_id:item_leche; cantidad:2.0; unidad:litros; categoria:lacteos -->\n",
    )

    respuesta = cliente.delete("/api/shopping-list/item_leche")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"item_id": "item_leche", "eliminadas": 1}
    texto = (vault_path / "listas" / "compra.md").read_text(encoding="utf-8")
    assert "item_leche" not in texto


def test_api_borrar_entrada_lista_no_encontrada(
    cliente: TestClient, vault_path
) -> None:
    """DELETE devuelve 404 si no hay línea pendiente para ese item_id."""
    _escribir_lista(vault_path, "# Lista de la compra\n\n")

    respuesta = cliente.delete("/api/shopping-list/item_leche")

    assert respuesta.status_code == 404


def test_api_editar_entrada_lista(cliente: TestClient, vault_path) -> None:
    """PUT /api/shopping-list/{item_id} edita una línea pendiente."""
    _escribir_lista(
        vault_path,
        "# Lista de la compra\n\n"
        "- [ ] Leche <!-- item_id:item_leche; cantidad:2.0; unidad:litros; categoria:lacteos -->\n",
    )

    respuesta = cliente.put(
        "/api/shopping-list/item_leche",
        json={"cantidad": 5.0, "unidad": "botellas"},
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == {"item_id": "item_leche", "editadas": 1}
    texto = (vault_path / "listas" / "compra.md").read_text(encoding="utf-8")
    assert "cantidad:5.0" in texto
    assert "unidad:botellas" in texto


def test_api_editar_entrada_lista_no_encontrada(
    cliente: TestClient, vault_path
) -> None:
    """PUT devuelve 404 si no hay línea pendiente para ese item_id."""
    _escribir_lista(vault_path, "# Lista de la compra\n\n")

    respuesta = cliente.put(
        "/api/shopping-list/item_leche", json={"cantidad": 1.0}
    )

    assert respuesta.status_code == 404
