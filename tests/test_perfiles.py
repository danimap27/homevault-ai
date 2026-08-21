"""Tests del CRUD de perfiles estilo Netflix."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def cliente(vault_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient con vault temporal para tests de perfiles."""
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    with TestClient(app) as cliente:
        yield cliente


def test_listar_perfiles_incluye_yo(cliente: TestClient) -> None:
    """Al arrancar sin perfiles existe el perfil por defecto 'Yo'."""
    respuesta = cliente.get("/api/profiles")
    assert respuesta.status_code == 200
    perfiles = respuesta.json()
    assert len(perfiles) == 1
    assert perfiles[0]["id"] == "yo"
    assert perfiles[0]["nombre"] == "Yo"


def test_crear_perfil(cliente: TestClient) -> None:
    """POST /api/profiles crea un perfil nuevo."""
    respuesta = cliente.post(
        "/api/profiles",
        json={
            "id": "ninos",
            "nombre": "Niños",
            "avatar": "🧒",
            "color": "#ff0000",
            "pin": "1234",
        },
    )
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["id"] == "ninos"
    assert datos["pin"] == "1234"


def test_limite_8_perfiles(cliente: TestClient) -> None:
    """No se pueden crear más de 8 perfiles (incluido el perfil por defecto)."""
    # El perfil "yo" ya existe; creamos 7 más para llegar al límite de 8
    for i in range(1, 8):
        respuesta = cliente.post(
            "/api/profiles",
            json={"id": f"perfil_{i}", "nombre": f"Perfil {i}"},
        )
        assert respuesta.status_code == 201, f"fallo en perfil {i}"

    respuesta = cliente.post(
        "/api/profiles",
        json={"id": "perfil_extra", "nombre": "Perfil extra"},
    )
    assert respuesta.status_code == 400


def test_verificar_pin_correcto(cliente: TestClient) -> None:
    """verify-pin con el PIN correcto devuelve valido true."""
    cliente.post(
        "/api/profiles",
        json={"id": "protegido", "nombre": "Protegido", "pin": "5678"},
    )
    respuesta = cliente.post(
        "/api/profiles/protegido/verify-pin", json={"pin": "5678"}
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["valido"] is True


def test_verificar_pin_incorrecto(cliente: TestClient) -> None:
    """verify-pin con PIN incorrecto devuelve valido false."""
    cliente.post(
        "/api/profiles",
        json={"id": "protegido", "nombre": "Protegido", "pin": "5678"},
    )
    respuesta = cliente.post(
        "/api/profiles/protegido/verify-pin", json={"pin": "0000"}
    )
    assert respuesta.json()["valido"] is False


def test_verificar_sin_pin(cliente: TestClient) -> None:
    """Un perfil sin PIN siempre es válido."""
    respuesta = cliente.post("/api/profiles/yo/verify-pin", json={"pin": ""})
    assert respuesta.status_code == 200
    assert respuesta.json()["valido"] is True


def test_no_borrar_ultimo_perfil(cliente: TestClient) -> None:
    """No se permite eliminar el único perfil existente."""
    respuesta = cliente.delete("/api/profiles/yo")
    assert respuesta.status_code == 400


def test_borrar_perfil(cliente: TestClient) -> None:
    """Se puede borrar un perfil si queda al menos otro."""
    cliente.post(
        "/api/profiles", json={"id": "invitado", "nombre": "Invitado"}
    )
    respuesta = cliente.delete("/api/profiles/invitado")
    assert respuesta.status_code == 204


def test_actualizar_perfil(cliente: TestClient) -> None:
    """PUT actualiza los campos editables de un perfil."""
    respuesta = cliente.put(
        "/api/profiles/yo",
        json={"nombre": "Daniel", "avatar": "🧔", "pin": "4321"},
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["nombre"] == "Daniel"
    assert datos["avatar"] == "🧔"
    assert datos["pin"] == "4321"


def test_persistencia_json(cliente: TestClient, vault_path: Path) -> None:
    """Los perfiles se persisten en vault/config/perfiles.json."""
    cliente.post(
        "/api/profiles",
        json={"id": "persistido", "nombre": "Persistido"},
    )
    ruta = vault_path / "config" / "perfiles.json"
    assert ruta.exists()
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    ids = [p["id"] for p in datos]
    assert "yo" in ids
    assert "persistido" in ids
