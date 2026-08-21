"""Tests del ReceiptParser y del registro en cascada de compras (Fase 3)."""

from __future__ import annotations

import json
from datetime import date

import frontmatter
import pytest

from backend.ai_vision_parser import (
    ErrorParseoTicket,
    GastoMes,
    ItemTicket,
    ReceiptParser,
    TicketParseado,
    _slugificar,
    register_purchase,
)
from backend.models import Consumible
from backend.vault_manager import VaultManager
from conftest import FakeLLM

# Ticket de ejemplo: un ítem que ya existe en el vault poblado
TICKET_JSON_EXISTENTE = json.dumps(
    {
        "comercio": "Mercadona",
        "fecha": "2026-08-15",
        "total_ticket": 12.5,
        "items": [
            {
                "nombre_detectado": "Yogur natural pack 4",
                "item_id_sugerido": "item_test_01",
                "cantidad": 4,
                "unidad": "unidades",
                "precio_unitario": 0.6,
                "categoria_sugerida": "lacteos",
                "ubicacion_sugerida": "nevera",
                "fecha_caducidad_estimada": "2026-09-01",
            }
        ],
    }
)

# Ticket de ejemplo con un ítem que no existe en el vault
TICKET_JSON_NUEVO = json.dumps(
    {
        "comercio": "Lidl",
        "fecha": "2026-08-15",
        "total_ticket": 7.0,
        "items": [
            {
                "nombre_detectado": "Pizza barbacoa",
                "item_id_sugerido": None,
                "cantidad": 2,
                "unidad": "unidades",
                "precio_unitario": 3.5,
                "categoria_sugerida": "congelados",
                "ubicacion_sugerida": "congelador",
                "fecha_caducidad_estimada": "2027-02-01",
            }
        ],
    }
)


# --- Parseo tolerante de la respuesta del LLM -------------------------------------


async def test_parseo_json_valido(
    vault_poblado: VaultManager, fake_llm: FakeLLM
) -> None:
    """JSON directo del LLM se valida como TicketParseado."""
    fake_llm.respuestas.append(TICKET_JSON_EXISTENTE)
    parser = ReceiptParser(vault_poblado, fake_llm)

    ticket = await parser.parse_ticket_from_text("4 yogures a 0.60")

    assert ticket.comercio == "Mercadona"
    assert ticket.fecha == date(2026, 8, 15)
    assert ticket.total_ticket == 12.5
    assert len(ticket.items) == 1
    assert ticket.items[0].item_id_sugerido == "item_test_01"
    # El prompt incluye el inventario para que el LLM sugiera item_id
    assert "item_test_01" in fake_llm.llamadas[0]["prompt"]
    assert "Yogur natural" in fake_llm.llamadas[0]["prompt"]


async def test_parseo_json_con_fence_markdown(
    vault: VaultManager, fake_llm: FakeLLM
) -> None:
    """JSON dentro de fences ```json se extrae correctamente."""
    fake_llm.respuestas.append(
        f"Aquí tienes el ticket:\n```json\n{TICKET_JSON_NUEVO}\n```\n"
    )
    parser = ReceiptParser(vault, fake_llm)

    ticket = await parser.parse_ticket_from_text("2 pizzas")

    assert ticket.comercio == "Lidl"
    assert ticket.items[0].nombre_detectado == "Pizza barbacoa"


async def test_parseo_json_envuelto_en_texto(
    vault: VaultManager, fake_llm: FakeLLM
) -> None:
    """JSON rodeado de texto libre se extrae por llaves extremas."""
    fake_llm.respuestas.append(
        f"El ticket parseado es: {TICKET_JSON_EXISTENTE} Espero que sirva."
    )
    parser = ReceiptParser(vault, fake_llm)

    ticket = await parser.parse_ticket_from_text("texto cualquiera")

    assert ticket.total_ticket == 12.5


async def test_parseo_json_invalido_error_estructurado(
    vault: VaultManager, fake_llm: FakeLLM
) -> None:
    """Respuesta sin JSON lanza ErrorParseoTicket."""
    fake_llm.respuestas.append("Lo siento, no puedo leer ese ticket.")
    parser = ReceiptParser(vault, fake_llm)

    with pytest.raises(ErrorParseoTicket):
        await parser.parse_ticket_from_text("texto ilegible")


async def test_parseo_json_esquema_invalido(
    vault: VaultManager, fake_llm: FakeLLM
) -> None:
    """JSON válido pero fuera de esquema lanza ErrorParseoTicket."""
    fake_llm.respuestas.append('{"comercio": 123, "items": "no-es-lista"}')
    parser = ReceiptParser(vault, fake_llm)

    with pytest.raises(ErrorParseoTicket):
        await parser.parse_ticket_from_text("texto")


async def test_parseo_imagen_pasa_bytes_al_llm(
    vault: VaultManager, fake_llm: FakeLLM
) -> None:
    """La imagen llega al LLM con sus bytes y mime type."""
    fake_llm.respuestas.append(TICKET_JSON_EXISTENTE)
    parser = ReceiptParser(vault, fake_llm)

    ticket = await parser.parse_ticket_from_image(
        b"\xff\xd8\xff", mime_type="image/jpeg"
    )

    assert ticket.comercio == "Mercadona"
    assert fake_llm.llamadas[0]["imagen"] == b"\xff\xd8\xff"
    assert fake_llm.llamadas[0]["mime_type"] == "image/jpeg"


async def test_datos_conocidos_tienen_prioridad(
    vault: VaultManager, fake_llm: FakeLLM
) -> None:
    """Comercio/total del llamador rellenan lo que el LLM no extrajo."""
    fake_llm.respuestas.append(
        json.dumps({"items": [], "comercio": "Desconocido", "total_ticket": 0})
    )
    parser = ReceiptParser(vault, fake_llm)

    ticket = await parser.parse_ticket_from_text(
        "texto", comercio="Aldi", total=23.4
    )

    assert ticket.comercio == "Aldi"
    assert ticket.total_ticket == 23.4


# --- Registro en cascada ------------------------------------------------------------


async def test_register_purchase_item_existente(
    vault_poblado: VaultManager,
) -> None:
    """Ítem existente: nuevo lote FIFO, stock al alza y [x] en la lista."""
    item = await vault_poblado.get_item("item_test_01")
    assert item is not None
    # El ítem estaba pendiente en la lista de la compra
    await vault_poblado._add_to_shopping_list(item)

    ticket = TicketParseado.model_validate(json.loads(TICKET_JSON_EXISTENTE))
    resultado = await register_purchase(vault_poblado, ticket)

    assert resultado.items[0].accion == "lote_anadido"
    assert resultado.items[0].tachado_de_lista_compra is True
    assert resultado.items[0].stock_actual == 10.0  # 6 + 4

    actualizado = await vault_poblado.get_item("item_test_01")
    assert actualizado is not None
    assert len(actualizado.lotes) == 3  # lot_01, lot_02 + nuevo
    assert actualizado.lotes[-1].fecha_caducidad == date(2026, 9, 1)
    assert actualizado.precio_unitario_estimado == 0.6

    entradas = await vault_poblado.get_shopping_list()
    yogur = [e for e in entradas if e.item_id == "item_test_01"]
    assert len(yogur) == 1
    assert yogur[0].comprado is True


async def test_register_purchase_item_nuevo(vault_poblado: VaultManager) -> None:
    """Ítem nuevo: crea el .md en la ubicación sugerida con esquema Fase 1."""
    ticket = TicketParseado.model_validate(json.loads(TICKET_JSON_NUEVO))
    resultado = await register_purchase(vault_poblado, ticket)

    assert resultado.items[0].accion == "item_creado"
    assert resultado.items[0].item_id == "item_pizza_barbacoa"
    assert resultado.items[0].stock_actual == 2.0  # stock 0 + compra

    ruta = (
        vault_poblado.vault_path
        / "inventario"
        / "congelador"
        / "item_pizza_barbacoa.md"
    )
    assert ruta.exists()
    post = frontmatter.loads(ruta.read_text(encoding="utf-8"))
    creado = Consumible.model_validate(post.metadata)
    assert creado.id == "item_pizza_barbacoa"
    assert creado.nombre == "Pizza barbacoa"
    assert creado.categoria == "congelados"
    assert creado.ubicacion == "congelador"
    assert creado.stock_actual == 2.0
    assert creado.stock_minimo == 1.0
    assert creado.auto_lista_compra is True
    assert len(creado.lotes) == 1
    assert creado.lotes[0].fecha_caducidad == date(2027, 2, 1)


async def test_register_purchase_campos_sugeridos_invalidos(
    vault: VaultManager,
) -> None:
    """Sugerencias fuera de catálogo caen a defaults seguros de Fase 1."""
    ticket = TicketParseado(
        comercio="Test",
        fecha=date(2026, 8, 15),
        total_ticket=1.0,
        items=[
            ItemTicket(
                nombre_detectado="Cosa rara",
                cantidad=1,
                unidad="sacos",
                categoria_sugerida="otros",
                ubicacion_sugerida="ático",
            )
        ],
    )
    resultado = await register_purchase(vault, ticket)

    creado = await vault.get_item(resultado.items[0].item_id)
    assert creado is not None
    assert creado.unidad == "unidades"
    assert creado.categoria == "despensa_seca"
    assert creado.ubicacion == "despensa"


async def test_registro_gastos_acumulativo_mismo_mes(
    vault: VaultManager,
) -> None:
    """Dos tickets del mismo mes suman total_mes en gastos/YYYY-MM.md."""
    ticket_1 = TicketParseado(
        comercio="Mercadona", fecha=date(2026, 8, 10), total_ticket=10.0
    )
    ticket_2 = TicketParseado(
        comercio="Lidl",
        fecha=date(2026, 8, 20),
        total_ticket=5.5,
        items=[ItemTicket(nombre_detectado="Pan", cantidad=1)],
    )
    await register_purchase(vault, ticket_1)
    resultado = await register_purchase(vault, ticket_2)

    assert resultado.archivo_gasto == "gastos/2026-08.md"
    assert resultado.total_mes == 15.5

    ruta = vault.vault_path / "gastos" / "2026-08.md"
    assert ruta.exists()
    post = frontmatter.loads(ruta.read_text(encoding="utf-8"))
    gasto = GastoMes.model_validate(post.metadata)
    assert gasto.mes == "2026-08"
    assert gasto.total_mes == 15.5
    assert len(gasto.tickets) == 2
    assert gasto.tickets[0].comercio == "Mercadona"
    assert gasto.tickets[1].comercio == "Lidl"
    # El cuerpo lleva la tabla Markdown con ambos tickets
    assert "| 2026-08-10 | Mercadona | 10.00 |" in post.content
    assert "| 2026-08-20 | Lidl | 5.50 |" in post.content


async def test_gastos_meses_distintos_archivos_distintos(
    vault: VaultManager,
) -> None:
    """Tickets de meses distintos generan archivos independientes."""
    await register_purchase(
        vault, TicketParseado(fecha=date(2026, 8, 31), total_ticket=3.0)
    )
    await register_purchase(
        vault, TicketParseado(fecha=date(2026, 9, 1), total_ticket=4.0)
    )
    assert (vault.vault_path / "gastos" / "2026-08.md").exists()
    assert (vault.vault_path / "gastos" / "2026-09.md").exists()


def test_slugificar() -> None:
    """El slug es ASCII snake_case determinista."""
    assert _slugificar("Pizza barbacoa") == "pizza_barbacoa"
    assert _slugificar("Atún claro (lata)") == "atun_claro_lata"
    assert _slugificar("Leche  entera") == "leche_entera"
