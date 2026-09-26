"""Tests de la merma/desperdicio: register_waste, resumen y endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.vault_manager import VaultManager
from conftest import escribir_md, metadata_item_limpieza


async def test_register_waste_descuenta_lote_fifo(
    vault_poblado: VaultManager,
) -> None:
    """La merma descuenta del lote con caducidad más próxima (FIFO)."""
    registro, item = await vault_poblado.register_waste(
        "item_test_01", 1.0, "caducado"
    )
    # El yogur de prueba tiene lotes [2.0 (22-ago), 4.0 (30-ago)]
    lotes = {l.id_lote: l.cantidad for l in item.lotes}
    assert lotes["lot_01"] == 1.0
    assert lotes["lot_02"] == 4.0
    assert registro.cantidad == 1.0
    assert registro.motivo == "caducado"
    assert registro.valor_estimado == pytest.approx(0.5)  # precio 0.5/u


async def test_register_waste_al_agotar_lotes_toca_stock(
    vault_path: Path,
) -> None:
    """Cuando los lotes no cubren la merma, el resto sale del stock suelto."""
    escribir_md(
        vault_path,
        "inventario/nevera",
        "queso.md",
        {
            "id": "item_queso",
            "nombre": "Queso curado",
            "categoria": "lacteos",
            "ubicacion": "nevera",
            "stock_actual": 5.0,
            "stock_minimo": 1.0,
            "unidad": "unidades",
            "precio_unitario_estimado": 2.0,
            "lotes": [
                {"id_lote": "q1", "cantidad": 1.0, "fecha_caducidad": "2026-09-01"},
                {"id_lote": "q2", "cantidad": 2.0, "fecha_caducidad": "2026-10-01"},
            ],
        },
    )
    vault = VaultManager(vault_path)
    _, item = await vault.register_waste("item_queso", 4.0, "caducado")
    assert item.lotes == []
    assert item.stock_actual == pytest.approx(4.0)  # 5 - (4 - 3 de lotes)


async def test_register_waste_valida_cantidad(vault_poblado: VaultManager) -> None:
    with pytest.raises(ValueError):
        await vault_poblado.register_waste("item_test_01", 0.0)
    with pytest.raises(ValueError, match="Stock insuficiente"):
        await vault_poblado.register_waste("item_test_01", 100.0)
    with pytest.raises(KeyError):
        await vault_poblado.register_waste("no_existe", 1.0)


async def test_register_waste_escribe_documento_mensual(
    vault_poblado: VaultManager,
) -> None:
    """El registro se vuelca en gastos/desperdicio-YYYY-MM.md con su tabla."""
    mes = datetime.now(timezone.utc).strftime("%Y-%m")
    await vault_poblado.register_waste("item_test_01", 1.0, "caducado")
    await vault_poblado.register_waste("item_test_01", 2.0, "no_deseado")

    ruta = vault_poblado.vault_path / "gastos" / f"desperdicio-{mes}.md"
    assert ruta.exists()
    texto = ruta.read_text(encoding="utf-8")
    assert "total_registros: 2" in texto
    assert "| caducado |" in texto
    assert "| no_deseado |" in texto

    resumen = await vault_poblado.resumen_desperdicio(mes)
    assert resumen.total_registros == 2
    assert resumen.valor_total == pytest.approx(1.5)  # 3 unidades x 0.5
    assert resumen.por_motivo == {"caducado": 1, "no_deseado": 1}
    # Los últimos van primero
    assert resumen.ultimos[0].motivo == "no_deseado"


async def test_resumen_desperdicio_mes_vacio(vault_poblado: VaultManager) -> None:
    resumen = await vault_poblado.resumen_desperdicio("2020-01")
    assert resumen.total_registros == 0
    assert resumen.valor_total == 0.0


async def test_waste_no_toca_ultimo_consumo(vault_poblado: VaultManager) -> None:
    """Una merma no altera ultimo_consumo (eso es solo para consumos reales)."""
    item_antes = await vault_poblado.get_item("item_test_01")
    assert item_antes is not None
    _, item = await vault_poblado.register_waste("item_test_01", 1.0)
    assert item.ultimo_consumo == item_antes.ultimo_consumo
    assert item.historial_consumo == item_antes.historial_consumo


# --- Endpoints -----------------------------------------------------------------


@pytest.fixture
def cliente(vault_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient de la app completa con el vault temporal."""
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    with TestClient(app) as cliente:
        yield cliente


def test_endpoint_waste_ok(cliente: TestClient, vault_path: Path) -> None:
    escribir_md(vault_path, "inventario/limpieza", "lejia.md", metadata_item_limpieza())
    respuesta = cliente.post(
        "/api/inventory/item_lejia/waste",
        json={"cantidad": 2, "motivo": "caducado"},
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["item_id"] == "item_lejia"
    assert datos["stock_actual"] == pytest.approx(3.0)
    assert datos["resumen_mes"]["total_registros"] == 1


def test_endpoint_waste_cantidad_invalida(
    cliente: TestClient, vault_path: Path
) -> None:
    escribir_md(vault_path, "inventario/limpieza", "lejia.md", metadata_item_limpieza())
    respuesta = cliente.post(
        "/api/inventory/item_lejia/waste",
        json={"cantidad": 50, "motivo": "caducado"},
    )
    assert respuesta.status_code == 400


def test_endpoint_waste_item_inexistente(cliente: TestClient) -> None:
    respuesta = cliente.post(
        "/api/inventory/no_existe/waste",
        json={"cantidad": 1},
    )
    assert respuesta.status_code == 404


def test_endpoint_waste_motivo_invalido(
    cliente: TestClient, vault_path: Path
) -> None:
    escribir_md(vault_path, "inventario/limpieza", "lejia.md", metadata_item_limpieza())
    respuesta = cliente.post(
        "/api/inventory/item_lejia/waste",
        json={"cantidad": 1, "motivo": "porque_si"},
    )
    assert respuesta.status_code == 422  # validación del Literal


def test_endpoint_resumen_waste(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/insights/waste")
    assert respuesta.status_code == 200
    assert respuesta.json()["total_registros"] == 0
    mala = cliente.get("/api/insights/waste", params={"mes": "2026-9"})
    assert mala.status_code == 400
