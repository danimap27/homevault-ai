"""Tests de la lógica del planificador de cocina (Fase 4c)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.models import Consumible
from backend.planner import DIAS_MAX_CONGELADOR_DEFECTO, Planner
from backend.vault_manager import VaultManager
from conftest import escribir_md


def metadata_item(item_id: str, nombre: str, **overrides) -> dict:
    """Frontmatter base de un consumible con fechas relativas a hoy."""
    metadata = {
        "id": item_id,
        "nombre": nombre,
        "categoria": "despensa_seca",
        "ubicacion": "despensa",
        "stock_actual": 5.0,
        "stock_minimo": 1.0,
        "unidad": "unidades",
        "lotes": [],
        "auto_lista_compra": False,
    }
    metadata.update(overrides)
    return metadata


def metadata_receta(
    receta_id: str, titulo: str, ingredientes: list[dict], **overrides
) -> dict:
    """Frontmatter base de una receta."""
    metadata = {
        "id": receta_id,
        "titulo": titulo,
        "categoria": "comida",
        "tiempo_minutos": 30,
        "raciones": 2,
        "ingredientes": ingredientes,
    }
    metadata.update(overrides)
    return metadata


def item_que_caduca(dias: int, **overrides) -> dict:
    """Metadata de un ítem que caduca en `dias` días."""
    fecha = (date.today() + timedelta(days=dias)).isoformat()
    return metadata_item(
        overrides.pop("id"),
        overrides.pop("nombre"),
        fecha_caducidad_proxima=fecha,
        lotes=[],
        **overrides,
    )


# --- Rescue Chef ---------------------------------------------------------------


async def test_rescue_chef_sugiere_solo_recetas_con_items_por_caducar(
    vault: VaultManager,
) -> None:
    escribir_md(
        vault.vault_path,
        "inventario/nevera",
        "pollo.md",
        item_que_caduca(2, id="item_pollo", nombre="Pollo"),
    )
    escribir_md(
        vault.vault_path,
        "inventario/despensa",
        "arroz.md",
        item_que_caduca(60, id="item_arroz", nombre="Arroz"),
    )
    escribir_md(
        vault.vault_path,
        "recetas",
        "pollo-al-ajillo.md",
        metadata_receta(
            "receta_pollo",
            "Pollo al ajillo",
            [{"item_id": "item_pollo", "nombre": "Pollo", "cantidad": 1, "unidad": "unidades"}],
        ),
    )
    escribir_md(
        vault.vault_path,
        "recetas",
        "arroz-blanco.md",
        metadata_receta(
            "receta_arroz",
            "Arroz blanco",
            [{"item_id": "item_arroz", "nombre": "Arroz", "cantidad": 200, "unidad": "gramos"}],
        ),
    )

    sugerencias = await Planner(vault).rescue_chef(dias=4)

    assert [s.receta.id for s in sugerencias] == ["receta_pollo"]
    assert sugerencias[0].items_a_rescatar[0].item_id == "item_pollo"
    assert sugerencias[0].dias_restantes_min == 2


async def test_rescue_chef_ordena_por_urgencia_y_cantidad_rescatada(
    vault: VaultManager,
) -> None:
    # Receta A usa un ítem que caduca en 3 días; receta B usa dos que
    # caducan mañana. B debe ir primero (más urgente).
    escribir_md(
        vault.vault_path, "inventario/nevera", "a.md",
        item_que_caduca(3, id="item_a", nombre="A"),
    )
    escribir_md(
        vault.vault_path, "inventario/nevera", "b.md",
        item_que_caduca(1, id="item_b", nombre="B"),
    )
    escribir_md(
        vault.vault_path, "inventario/nevera", "c.md",
        item_que_caduca(1, id="item_c", nombre="C"),
    )
    escribir_md(
        vault.vault_path, "recetas", "ra.md",
        metadata_receta(
            "receta_a", "Receta A",
            [{"item_id": "item_a", "nombre": "A", "cantidad": 1, "unidad": "unidades"}],
        ),
    )
    escribir_md(
        vault.vault_path, "recetas", "rb.md",
        metadata_receta(
            "receta_b", "Receta B",
            [
                {"item_id": "item_b", "nombre": "B", "cantidad": 1, "unidad": "unidades"},
                {"item_id": "item_c", "nombre": "C", "cantidad": 1, "unidad": "unidades"},
            ],
        ),
    )

    sugerencias = await Planner(vault).rescue_chef(dias=4)

    assert [s.receta.id for s in sugerencias] == ["receta_b", "receta_a"]
    assert len(sugerencias[0].items_a_rescatar) == 2


async def test_rescue_chef_marca_stock_critico(vault: VaultManager) -> None:
    escribir_md(
        vault.vault_path, "inventario/nevera", "pollo.md",
        item_que_caduca(
            2,
            id="item_pollo", nombre="Pollo",
            stock_actual=0.5, stock_minimo=1.0,
        ),
    )
    escribir_md(
        vault.vault_path, "recetas", "pollo.md",
        metadata_receta(
            "receta_pollo", "Pollo al ajillo",
            [{"item_id": "item_pollo", "nombre": "Pollo", "cantidad": 1, "unidad": "unidades"}],
        ),
    )

    sugerencias = await Planner(vault).rescue_chef(dias=4)

    assert sugerencias[0].stock_critico is True


async def test_rescue_chef_sin_caducidades_devuelve_vacio(
    vault: VaultManager,
) -> None:
    escribir_md(
        vault.vault_path, "inventario/despensa", "arroz.md",
        metadata_item("item_arroz", "Arroz"),
    )
    assert await Planner(vault).rescue_chef(dias=4) == []


# --- Batch cooking ---------------------------------------------------------------


async def test_batch_cooking_descuenta_ingredientes_y_crea_tupper(
    vault: VaultManager,
) -> None:
    hoy = date.today()
    escribir_md(
        vault.vault_path, "inventario/despensa", "pasta.md",
        metadata_item(
            "item_pasta", "Espaguetis",
            stock_actual=500.0, unidad="gramos",
            lotes=[{
                "id_lote": "lot_01",
                "cantidad": 300.0,
                "fecha_caducidad": (hoy + timedelta(days=10)).isoformat(),
            }],
        ),
    )
    escribir_md(
        vault.vault_path, "recetas", "pasta.md",
        metadata_receta(
            "receta_pasta", "Pasta con tomate",
            [
                {"item_id": "item_pasta", "nombre": "Espaguetis", "cantidad": 400, "unidad": "gramos"},
                {"item_id": None, "nombre": "Sal", "cantidad": 1, "unidad": "unidades"},
            ],
            raciones=4,
        ),
    )

    resultado = await Planner(vault).batch_cooking(["receta_pasta"])

    # Ingrediente vinculado consumido vía FIFO (300 del lote + 100 de stock;
    # consume_item solo descuenta de stock_actual lo no cubierto por lotes)
    item = await vault.get_item("item_pasta")
    assert item is not None
    assert item.stock_actual == pytest.approx(400.0)
    assert item.lotes == []

    # Ingrediente sin item_id queda omitido pero registrado
    sal = [i for i in resultado.ingredientes if i.nombre == "Sal"][0]
    assert sal.consumido is False

    # Tupper creado en inventario/congelador/ con el esquema Consumible
    assert len(resultado.tuppers) == 1
    tupper = resultado.tuppers[0]
    assert tupper.ruta.startswith("inventario/congelador/")
    ruta = vault.vault_path / tupper.ruta
    assert ruta.exists()
    creado, _ = await vault._read_doc(ruta, Consumible)
    assert creado.categoria == "congelados"
    assert creado.ubicacion == "congelador"
    assert creado.unidad == "unidades"
    assert creado.stock_actual == pytest.approx(4.0)
    assert creado.fecha_congelacion == hoy
    assert creado.fecha_caducidad_proxima == hoy + timedelta(
        days=DIAS_MAX_CONGELADOR_DEFECTO
    )


async def test_batch_cooking_respeta_dias_max_congelador(
    vault: VaultManager,
) -> None:
    escribir_md(
        vault.vault_path, "recetas", "sopa.md",
        metadata_receta("receta_sopa", "Sopa de verduras", []),
    )

    resultado = await Planner(vault).batch_cooking(
        ["receta_sopa"], dias_max_congelador=30
    )

    assert resultado.tuppers[0].fecha_caducidad == date.today() + timedelta(days=30)


async def test_batch_cooking_receta_inexistente(vault: VaultManager) -> None:
    with pytest.raises(KeyError):
        await Planner(vault).batch_cooking(["receta_fantasma"])


async def test_batch_cooking_destino_invalido(vault: VaultManager) -> None:
    escribir_md(
        vault.vault_path, "recetas", "sopa.md",
        metadata_receta("receta_sopa", "Sopa de verduras", []),
    )
    with pytest.raises(ValueError):
        await Planner(vault).batch_cooking(["receta_sopa"], destino="luna")


async def test_batch_cooking_ingrediente_no_inventariado(
    vault: VaultManager,
) -> None:
    escribir_md(
        vault.vault_path, "recetas", "sopa.md",
        metadata_receta(
            "receta_sopa", "Sopa",
            [{"item_id": "item_fantasma", "nombre": "Nada", "cantidad": 1, "unidad": "unidades"}],
        ),
    )

    resultado = await Planner(vault).batch_cooking(["receta_sopa"])

    assert resultado.ingredientes[0].consumido is False
    assert "no encontrado" in resultado.ingredientes[0].detalle
    assert len(resultado.tuppers) == 1  # el tupper se crea igualmente


# --- Modo evento -------------------------------------------------------------------


async def test_modo_evento_anade_solo_faltantes_a_la_lista(
    vault: VaultManager,
) -> None:
    escribir_md(
        vault.vault_path, "inventario/despensa", "pasta.md",
        metadata_item("item_pasta", "Espaguetis", stock_actual=100.0, unidad="gramos"),
    )
    escribir_md(
        vault.vault_path, "inventario/despensa", "tomate.md",
        metadata_item("item_tomate", "Tomate frito", stock_actual=10.0, unidad="unidades"),
    )
    escribir_md(
        vault.vault_path, "recetas", "pasta.md",
        metadata_receta(
            "receta_pasta", "Pasta con tomate",
            [
                {"item_id": "item_pasta", "nombre": "Espaguetis", "cantidad": 200, "unidad": "gramos"},
                {"item_id": "item_tomate", "nombre": "Tomate frito", "cantidad": 1, "unidad": "unidades"},
            ],
            raciones=2,
        ),
    )

    resultado = await Planner(vault).modo_evento(["receta_pasta"], invitados=4)

    # factor 4/2 = 2: pasta necesita 400g (stock 100 -> faltan 300);
    # tomate necesita 2 (stock 10 -> no falta)
    pasta = [f for f in resultado.faltantes if f.item_id == "item_pasta"][0]
    tomate = [f for f in resultado.faltantes if f.item_id == "item_tomate"][0]
    assert pasta.cantidad_necesaria == pytest.approx(400.0)
    assert pasta.faltante == pytest.approx(300.0)
    assert pasta.anadido_a_lista is True
    assert tomate.faltante == 0.0
    assert tomate.anadido_a_lista is False

    lista = await vault.get_shopping_list()
    assert len(lista) == 1
    assert lista[0].nombre == "Espaguetis"
    assert lista[0].cantidad == pytest.approx(300.0)


async def test_modo_evento_no_duplica_lineas_pendientes(
    vault: VaultManager,
) -> None:
    escribir_md(
        vault.vault_path, "inventario/despensa", "pasta.md",
        metadata_item("item_pasta", "Espaguetis", stock_actual=0.0, unidad="gramos"),
    )
    escribir_md(
        vault.vault_path, "recetas", "pasta.md",
        metadata_receta(
            "receta_pasta", "Pasta",
            [{"item_id": "item_pasta", "nombre": "Espaguetis", "cantidad": 200, "unidad": "gramos"}],
        ),
    )

    planner = Planner(vault)
    await planner.modo_evento(["receta_pasta"], invitados=2)
    await planner.modo_evento(["receta_pasta"], invitados=2)

    lista = await vault.get_shopping_list()
    assert len(lista) == 1


async def test_modo_evento_errores(vault: VaultManager) -> None:
    escribir_md(
        vault.vault_path, "recetas", "pasta.md",
        metadata_receta("receta_pasta", "Pasta", []),
    )
    with pytest.raises(KeyError):
        await Planner(vault).modo_evento(["receta_fantasma"], invitados=4)
    with pytest.raises(ValueError):
        await Planner(vault).modo_evento(["receta_pasta"], invitados=0)
