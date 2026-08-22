"""Tests del gestor y endpoints de supermercados."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.supermercados import SupermercadoManager


def _manager(vault_path: Path) -> SupermercadoManager:
    """Helper para instanciar el manager con un vault temporal."""
    return SupermercadoManager(vault_path)


def test_crea_archivo_por_defecto(vault_path: Path) -> None:
    """Si no existe el archivo, se crea Mercadona como predeterminado."""
    manager = _manager(vault_path)

    predeterminado = manager.obtener_predeterminado()

    assert predeterminado is not None
    assert predeterminado.id == "mercadona"
    assert predeterminado.nombre == "Mercadona"
    assert predeterminado.predeterminado is True


def test_listar_ordenado_por_nombre(vault_path: Path) -> None:
    """listar devuelve los supermercados ordenados por nombre."""
    manager = _manager(vault_path)
    manager.crear("Lidl")
    manager.crear("Aldi")

    nombres = [s.nombre for s in manager.listar()]

    assert nombres == ["Aldi", "Lidl", "Mercadona"]


def test_crear_primer_supermercado_es_predeterminado(
    vault_path: Path,
) -> None:
    """Al borrar el predeterminado y crear otro, el nuevo es predeterminado."""
    manager = _manager(vault_path)
    manager.borrar("mercadona")

    nuevo = manager.crear("Carrefour")

    assert nuevo.predeterminado is True
    assert manager.obtener_predeterminado().id == "carrefour"


def test_actualizar_predeterminado_unico(vault_path: Path) -> None:
    """Solo un supermercado puede ser predeterminado."""
    manager = _manager(vault_path)
    manager.crear("Lidl")

    manager.actualizar("lidl", predeterminado=True)

    predeterminados = [s for s in manager.listar() if s.predeterminado]
    assert len(predeterminados) == 1
    assert predeterminados[0].id == "lidl"


def test_borrar_predeterminado_asigna_otro(vault_path: Path) -> None:
    """Al borrar el predeterminado, otro pasa a serlo."""
    manager = _manager(vault_path)
    manager.crear("Lidl")

    manager.borrar("mercadona")

    assert manager.obtener_predeterminado().id == "lidl"


def test_borrar_unico_supermercado(vault_path: Path) -> None:
    """Se puede borrar el único supermercado; la lista queda vacía."""
    manager = _manager(vault_path)

    borrado = manager.borrar("mercadona")

    assert borrado is True
    assert manager.listar() == []
    assert manager.obtener_predeterminado() is None


def test_actualizar_supermercado_inexistente_lanza_keyerror(
    vault_path: Path,
) -> None:
    """actualizar lanza KeyError si el id no existe."""
    manager = _manager(vault_path)
    with pytest.raises(KeyError):
        manager.actualizar("inexistente", nombre="Nuevo")


@pytest.fixture
def cliente(vault_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient de la app completa con el vault temporal."""
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    with TestClient(app) as cliente:
        yield cliente


def test_api_crud_supermercados(cliente: TestClient) -> None:
    """GET/POST/PUT/DELETE de /api/supermarkets."""
    lista_inicial = cliente.get("/api/supermarkets").json()
    assert any(s["id"] == "mercadona" for s in lista_inicial)

    creado = cliente.post("/api/supermarkets", json={"nombre": "Lidl"})
    assert creado.status_code == 201
    assert creado.json()["id"] == "lidl"

    actualizado = cliente.put(
        "/api/supermarkets/lidl", json={"predeterminado": True}
    )
    assert actualizado.status_code == 200
    assert actualizado.json()["predeterminado"] is True

    # Mercadona ya no es predeterminado
    mercadona = next(
        s for s in cliente.get("/api/supermarkets").json() if s["id"] == "mercadona"
    )
    assert mercadona["predeterminado"] is False

    borrado = cliente.delete("/api/supermarkets/lidl")
    assert borrado.status_code == 204

    assert not any(s["id"] == "lidl" for s in cliente.get("/api/supermarkets").json())


def test_api_borrar_supermercado_inexistente_404(
    cliente: TestClient,
) -> None:
    """DELETE de un supermercado inexistente responde 404."""
    respuesta = cliente.delete("/api/supermarkets/inexistente")
    assert respuesta.status_code == 404
