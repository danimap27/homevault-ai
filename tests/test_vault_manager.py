"""Tests del VaultManager: FIFO, lista de la compra, huérfanos, concurrencia."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.models import Consumible
from backend.vault_manager import VaultManager


async def test_consume_fifo_lote_mas_proximo(
    vault_poblado: VaultManager,
) -> None:
    """Un consumo parcial descuenta primero del lote con caducidad más cercana."""
    resultado = await vault_poblado.consume_item("item_test_01", 1.0)

    assert resultado.cantidad_consumida_lotes == 1.0
    assert resultado.cantidad_consumida_stock == 0.0

    item = await vault_poblado.get_item("item_test_01")
    assert item is not None
    lotes = {l.id_lote: l for l in item.lotes}
    # lot_01 caduca el 2026-08-22 (antes que lot_02, 2026-08-30)
    assert lotes["lot_01"].cantidad == 1.0
    assert lotes["lot_02"].cantidad == 4.0
    # El stock_actual no se toca mientras queden lotes
    assert item.stock_actual == 6.0


async def test_consume_agota_lotes_y_descuenta_stock(
    vault_poblado: VaultManager,
) -> None:
    """Al agotar los lotes, el resto se descuenta de stock_actual."""
    # Lotes totales: 2 + 4 = 6 unidades; consumimos 7 -> 1 sale del stock
    resultado = await vault_poblado.consume_item("item_test_01", 7.0)

    assert resultado.cantidad_consumida_lotes == 6.0
    assert resultado.cantidad_consumida_stock == 1.0

    item = await vault_poblado.get_item("item_test_01")
    assert item is not None
    assert item.lotes == []
    assert item.stock_actual == 5.0


async def test_consume_recalcula_fecha_caducidad_proxima(
    vault_poblado: VaultManager,
) -> None:
    """fecha_caducidad_proxima es la mínima caducidad entre lotes restantes."""
    # Agotar lot_01 (el más próximo) -> la próxima caducidad pasa a lot_02
    await vault_poblado.consume_item("item_test_01", 2.0)
    item = await vault_poblado.get_item("item_test_01")
    assert item is not None
    assert item.fecha_caducidad_proxima == date(2026, 8, 30)

    # Agotar todos los lotes -> sin fecha próxima
    await vault_poblado.consume_item("item_test_01", 4.0)
    item = await vault_poblado.get_item("item_test_01")
    assert item is not None
    assert item.lotes == []
    assert item.fecha_caducidad_proxima is None


async def test_consume_actualiza_timestamps(
    vault_poblado: VaultManager,
) -> None:
    """ultimo_consumo y ultima_actualizacion se actualizan en UTC."""
    antes = datetime.now(timezone.utc)
    await vault_poblado.consume_item("item_test_01", 1.0)
    item = await vault_poblado.get_item("item_test_01")
    assert item is not None
    assert item.ultimo_consumo is not None
    assert item.ultimo_consumo >= antes
    assert item.ultima_actualizacion is not None
    assert item.ultima_actualizacion >= antes


async def test_trigger_lista_compra_al_caer_bajo_minimo(
    vault_poblado: VaultManager,
) -> None:
    """Al caer a/bajo del stock mínimo con auto_lista_compra, se añade a la lista."""
    # stock 6 -> consumir 5 desde lotes deja lotes en 1; consumir del stock
    # Mejor: consumir 6 (agota lotes) y luego 4 del stock -> stock 2 == mínimo
    await vault_poblado.consume_item("item_test_01", 6.0)
    resultado = await vault_poblado.consume_item("item_test_01", 4.0)

    assert resultado.bajo_minimo is True
    assert resultado.anadido_a_lista_compra is True

    lista = await vault_poblado.get_shopping_list()
    pendientes = [e for e in lista if e.item_id == "item_test_01"]
    assert len(pendientes) == 1
    assert pendientes[0].comprado is False
    assert pendientes[0].categoria == "lacteos"
    assert pendientes[0].cantidad is not None
    assert pendientes[0].cantidad > 0


async def test_trigger_lista_compra_no_duplica(
    vault_poblado: VaultManager,
) -> None:
    """Si el ítem ya está pendiente en la lista, no se añade de nuevo."""
    await vault_poblado.consume_item("item_test_01", 6.0)
    r1 = await vault_poblado.consume_item("item_test_01", 4.0)
    r2 = await vault_poblado.consume_item("item_test_01", 0.5)

    assert r1.anadido_a_lista_compra is True
    assert r2.anadido_a_lista_compra is False

    lista = await vault_poblado.get_shopping_list()
    assert len([e for e in lista if e.item_id == "item_test_01"]) == 1


async def test_add_purchase_crea_lote_y_tacha_lista(
    vault_poblado: VaultManager,
) -> None:
    """add_purchase crea lote único, sube stock y tacha el ítem de la lista."""
    await vault_poblado.consume_item("item_test_01", 6.0)
    await vault_poblado.consume_item("item_test_01", 4.0)

    resultado = await vault_poblado.add_purchase(
        "item_test_01", 5.0, 0.55, date(2026, 9, 15)
    )

    assert resultado.cantidad == 5.0
    assert resultado.stock_actual == 7.0
    assert resultado.tachado_de_lista_compra is True
    assert resultado.id_lote.startswith("lot_")

    item = await vault_poblado.get_item("item_test_01")
    assert item is not None
    ids = [l.id_lote for l in item.lotes]
    assert resultado.id_lote in ids
    assert len(ids) == len(set(ids))  # ids de lote únicos
    assert item.precio_unitario_estimado == 0.55
    assert item.fecha_caducidad_proxima == date(2026, 9, 15)

    lista = await vault_poblado.get_shopping_list()
    entrada = [e for e in lista if e.item_id == "item_test_01"][0]
    assert entrada.comprado is True


async def test_detector_huerfanos(vault: VaultManager) -> None:
    """Ítems con ultimo_consumo > 2x dias_promedio_consumo son huérfanos."""
    ahora = datetime.now(timezone.utc)
    huerfano = (ahora - timedelta(days=10)).isoformat()
    reciente = (ahora - timedelta(days=2)).isoformat()
    plantilla = """---
id: "{id}"
nombre: "{nombre}"
categoria: "despensa_seca"
ubicacion: "despensa"
stock_actual: 1.0
stock_minimo: 1.0
unidad: "unidades"
dias_promedio_consumo: 3.0
ultimo_consumo: "{ultimo}"
---

Cuerpo.
"""
    (vault.vault_path / "inventario" / "despensa" / "viejo.md").write_text(
        plantilla.format(
            id="item_viejo", nombre="Producto olvidado", ultimo=huerfano
        ),
        encoding="utf-8",
    )
    (vault.vault_path / "inventario" / "despensa" / "fresco.md").write_text(
        plantilla.format(
            id="item_fresco", nombre="Producto activo", ultimo=reciente
        ),
        encoding="utf-8",
    )

    huerfanos = await vault.find_orphan_items()

    assert [h.item_id for h in huerfanos] == ["item_viejo"]
    # 10 días desde el último consumo, umbral 6 días -> 4 de exceso
    assert huerfanos[0].dias_desde_ultimo_consumo == pytest.approx(10.0, abs=0.1)
    assert huerfanos[0].dias_exceso == pytest.approx(4.0, abs=0.1)


async def test_query_expiring_ordena_por_urgencia(
    vault_poblado: VaultManager,
) -> None:
    """query_expiring devuelve ítems dentro de la ventana, más urgente primero."""
    hoy = datetime.now(timezone.utc).date()
    plantilla = """---
id: "{id}"
nombre: "{nombre}"
categoria: "lacteos"
ubicacion: "nevera"
stock_actual: 1.0
stock_minimo: 0.0
unidad: "unidades"
fecha_caducidad_proxima: "{fecha}"
---

Cuerpo.
"""
    for i, dias in ((1, 1), (2, 3), (3, 30)):
        (
            vault_poblado.vault_path / "inventario" / "nevera" / f"cad_{i}.md"
        ).write_text(
            plantilla.format(
                id=f"item_cad_{i}",
                nombre=f"Caduca en {dias}",
                fecha=(hoy + timedelta(days=dias)).isoformat(),
            ),
            encoding="utf-8",
        )

    # Ventana de 4 días: entran los dos primeros, no el de 30 días
    resultados = await vault_poblado.query_expiring(4)
    ids = [r.item_id for r in resultados]
    assert "item_cad_3" not in ids
    assert ids.index("item_cad_1") < ids.index("item_cad_2")


async def test_concurrencia_consumes_no_corrompen(
    vault_poblado: VaultManager,
) -> None:
    """Consumes async simultáneos sobre el mismo archivo son consistentes."""
    n_tareas = 10
    await asyncio.gather(
        *(
            vault_poblado.consume_item("item_conc_01", 1.0)
            for _ in range(n_tareas)
        )
    )

    item = await vault_poblado.get_item("item_conc_01")
    assert item is not None
    # stock inicial 10.0, 10 consumos de 1.0 -> 0.0 exacto
    assert item.stock_actual == pytest.approx(10.0 - n_tareas)


async def test_busquedas(vault_poblado: VaultManager) -> None:
    """Búsqueda por id, nombre (substring case-insensitive) y EAN."""
    por_id = await vault_poblado.get_item("item_test_01")
    assert por_id is not None and por_id.nombre == "Yogur natural"

    por_nombre = await vault_poblado.search_by_name("YOGUR")
    assert [i.id for i in por_nombre] == ["item_test_01"]

    por_ean = await vault_poblado.get_item_by_ean("8411111111111")
    assert por_ean is not None and por_ean.id == "item_test_01"

    resuelto = await vault_poblado.resolve_item("yogur natural")
    assert resuelto is not None and resuelto.id == "item_test_01"


async def test_filtro_por_ubicacion(vault_poblado: VaultManager) -> None:
    """list_items filtra por ubicación."""
    nevera = await vault_poblado.list_items(ubicacion="nevera")
    assert [i.id for i in nevera] == ["item_test_01"]
    todos = await vault_poblado.list_items()
    assert len(todos) == 2


async def test_vault_ejemplo_valido(vault_ejemplo: VaultManager) -> None:
    """El vault de ejemplo del repo parsea y valida sin errores."""
    items = await vault_ejemplo.list_items()
    assert any(i.id == "item_milk_01" for i in items)


async def test_consumo_item_inexistente(vault_poblado: VaultManager) -> None:
    """Consumir un ítem inexistente lanza KeyError."""
    with pytest.raises(KeyError):
        await vault_poblado.consume_item("item_fantasma", 1.0)
