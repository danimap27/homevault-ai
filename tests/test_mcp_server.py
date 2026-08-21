"""Tests de las herramientas MCP de HomeVault AI (Fase 3).

Se testea la lógica de cada herramienta invocando directamente las funciones
`tool_*` con un ContextoHomeVault sobre el vault temporal, sin levantar el
transporte stdio. También se verifica que el MCPServer registra las 7
herramientas con sus nombres exactos.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from backend.ai_vision_parser import ReceiptParser
from backend.google_sync import GoogleSync
from backend.mcp_server import (
    ContextoHomeVault,
    create_mcp_server,
    tool_inventory_consume,
    tool_inventory_query_expiring,
    tool_inventory_record_purchase,
    tool_meal_plan_suggest,
    tool_shopping_list_get_and_modify,
    tool_task_list_pending,
    tool_task_mark_completed,
)
from backend.vault_manager import VaultManager
from conftest import (
    FakeCalendarClient,
    FakeLLM,
    FakeTasksClient,
    escribir_md,
    metadata_tarea_base,
)

TICKET_JSON = json.dumps(
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
            }
        ],
    }
)


@pytest.fixture
def ctx(
    vault_poblado: VaultManager,
    fake_tasks: FakeTasksClient,
    fake_calendar: FakeCalendarClient,
    fake_llm: FakeLLM,
) -> ContextoHomeVault:
    """Contexto MCP sobre el vault poblado con clientes fake."""
    sync = GoogleSync(
        vault_poblado, tasks_client=fake_tasks, calendar_client=fake_calendar
    )
    parser = ReceiptParser(vault_poblado, fake_llm)
    return ContextoHomeVault(vault=vault_poblado, sync=sync, parser=parser)


# --- inventory_record_purchase ------------------------------------------------------


async def test_record_purchase_texto_libre(ctx: ContextoHomeVault) -> None:
    """Texto libre: pasa por el LLM y actualiza inventario y gastos."""
    ctx.parser.llm.respuestas.append(TICKET_JSON)  # type: ignore[union-attr]

    resultado = await tool_inventory_record_purchase(
        ctx, "4 yogures de Mercadona por 12.50", "Mercadona", 12.5
    )

    assert resultado["ok"] is True
    assert resultado["items"][0]["accion"] == "lote_anadido"
    assert resultado["total_mes"] == 12.5
    assert resultado["archivo_gasto"] == "gastos/2026-08.md"
    item = await ctx.vault.get_item("item_test_01")
    assert item is not None
    assert item.stock_actual == 10.0


async def test_record_purchase_items_estructurados_sin_llm(
    ctx: ContextoHomeVault,
) -> None:
    """Lista estructurada: registro directo, sin necesidad de LLM."""
    ctx.parser = None  # sin proveedor de IA configurado

    resultado = await tool_inventory_record_purchase(
        ctx,
        [
            {
                "nombre_detectado": "Queso rallado",
                "cantidad": 1,
                "unidad": "unidades",
                "precio_unitario": 2.1,
                "categoria_sugerida": "lacteos",
                "ubicacion_sugerida": "nevera",
            }
        ],
        "Aldi",
        2.1,
    )

    assert resultado["ok"] is True
    assert resultado["items"][0]["accion"] == "item_creado"
    assert resultado["items"][0]["item_id"] == "item_queso_rallado"
    assert resultado["ticket"]["comercio"] == "Aldi"
    assert resultado["total_mes"] == 2.1


async def test_record_purchase_texto_sin_llm_error(
    ctx: ContextoHomeVault,
) -> None:
    """Texto libre sin parser configurado devuelve error estructurado."""
    ctx.parser = None

    resultado = await tool_inventory_record_purchase(ctx, "texto", "", 0.0)

    assert resultado["ok"] is False
    assert resultado["error"]["tipo"] == "RuntimeError"


# --- inventory_consume ----------------------------------------------------------------


async def test_consume_devuelve_stock_y_sin_alerta(
    ctx: ContextoHomeVault,
) -> None:
    """Consumo cubierto por lotes: FIFO descuenta lotes, sin alerta."""
    resultado = await tool_inventory_consume(ctx, "item_test_01", 2.0, "unidades")

    assert resultado["ok"] is True
    # Los lotes (2 + 4 unidades) cubren el consumo: stock_actual no baja
    assert resultado["cantidad_consumida_lotes"] == 2.0
    assert resultado["stock_actual"] == 6.0
    assert resultado["alerta_stock_minimo"] is False
    assert resultado["aviso_unidad"] is None


async def test_consume_resuelve_por_nombre_y_alerta_minimo(
    ctx: ContextoHomeVault,
) -> None:
    """Resolución por nombre + alerta al tocar el stock mínimo."""
    # 10 uds: agota los 6 de los lotes y baja stock_actual de 6 a 2 (= mínimo)
    resultado = await tool_inventory_consume(ctx, "Yogur", 10.0, "unidades")

    assert resultado["ok"] is True
    assert resultado["item_id"] == "item_test_01"
    assert resultado["stock_actual"] == 2.0  # toca stock_minimo=2
    assert resultado["alerta_stock_minimo"] is True
    assert resultado["anadido_a_lista_compra"] is True


async def test_consume_aviso_unidad_distinta(ctx: ContextoHomeVault) -> None:
    """Unidad distinta a la registrada genera aviso (pero no error)."""
    resultado = await tool_inventory_consume(ctx, "item_test_01", 1.0, "kg")

    assert resultado["ok"] is True
    assert "kg" in resultado["aviso_unidad"]


async def test_consume_item_no_encontrado(ctx: ContextoHomeVault) -> None:
    """Identificador inexistente devuelve error estructurado."""
    resultado = await tool_inventory_consume(ctx, "no_existo", 1.0, "unidades")

    assert resultado["ok"] is False
    assert resultado["error"]["tipo"] == "KeyError"


# --- inventory_query_expiring ----------------------------------------------------------


async def test_query_expiring(vault: VaultManager) -> None:
    """Solo los ítems dentro de la ventana aparecen en la respuesta."""
    caduca_pronto = (date.today() + timedelta(days=2)).isoformat()
    caduca_lejos = (date.today() + timedelta(days=30)).isoformat()
    escribir_md(
        vault.vault_path,
        "inventario/nevera",
        "pollo.md",
        {
            "id": "item_pollo",
            "nombre": "Pechuga de pollo",
            "categoria": "congelados",
            "ubicacion": "nevera",
            "stock_actual": 1.0,
            "stock_minimo": 0.0,
            "unidad": "kg",
            "fecha_caducidad_proxima": caduca_pronto,
        },
    )
    escribir_md(
        vault.vault_path,
        "inventario/despensa",
        "lentejas.md",
        {
            "id": "item_lentejas",
            "nombre": "Lentejas",
            "categoria": "despensa_seca",
            "ubicacion": "despensa",
            "stock_actual": 2.0,
            "stock_minimo": 0.0,
            "unidad": "kg",
            "fecha_caducidad_proxima": caduca_lejos,
        },
    )
    ctx = ContextoHomeVault(
        vault=vault, sync=GoogleSync(vault), parser=None
    )

    resultado = await tool_inventory_query_expiring(ctx, 4)

    assert resultado["ok"] is True
    ids = [i["item_id"] for i in resultado["items"]]
    assert ids == ["item_pollo"]
    assert resultado["items"][0]["dias_restantes"] == 2

    resultado_corto = await tool_inventory_query_expiring(ctx, 1)
    assert resultado_corto["items"] == []


# --- task_list_pending ------------------------------------------------------------------


async def test_task_list_pending_filtra_por_usuario(
    ctx: ContextoHomeVault,
) -> None:
    """Lista solo pendientes y respeta el filtro por usuario."""
    escribir_md(
        ctx.vault.vault_path, "tareas", "t1.md", metadata_tarea_base()
    )
    escribir_md(
        ctx.vault.vault_path,
        "tareas",
        "t2.md",
        metadata_tarea_base(
            id="tarea_test_02", titulo="Sacar la basura", asignado_a="Pareja"
        ),
    )
    escribir_md(
        ctx.vault.vault_path,
        "tareas",
        "t3.md",
        metadata_tarea_base(id="tarea_test_03", estado="completada"),
    )

    todas = await tool_task_list_pending(ctx)
    assert todas["ok"] is True
    assert {t["id"] for t in todas["tareas"]} == {
        "tarea_test_01",
        "tarea_test_02",
    }

    daniel = await tool_task_list_pending(ctx, assigned_user="Daniel")
    assert [t["id"] for t in daniel["tareas"]] == ["tarea_test_01"]


# --- task_mark_completed -----------------------------------------------------------------


async def test_task_mark_completed_flujo_completo(
    ctx: ContextoHomeVault,
) -> None:
    """Completa con rotación, reprogramación semanal e historial."""
    hoy = date.today()
    escribir_md(
        ctx.vault.vault_path,
        "tareas",
        "t1.md",
        metadata_tarea_base(fecha_programada=hoy.isoformat()),
    )

    resultado = await tool_task_mark_completed(ctx, "tarea_test_01", "Daniel")

    assert resultado["ok"] is True
    tarea = resultado["tarea"]
    assert tarea["estado"] == "pendiente"  # semanal: se reprograma
    assert tarea["fecha_programada"] == (hoy + timedelta(days=7)).isoformat()
    assert tarea["asignado_a"] == "Pareja"  # rotación Daniel -> Pareja
    assert len(tarea["historial_completados"]) == 1
    assert tarea["historial_completados"][0]["usuario"] == "Daniel"
    assert resultado["bloqueada_por_stock"] is False


async def test_task_mark_completed_no_encontrada(
    ctx: ContextoHomeVault,
) -> None:
    """Tarea inexistente devuelve error estructurado."""
    resultado = await tool_task_mark_completed(ctx, "no_existo", "Daniel")

    assert resultado["ok"] is False
    assert resultado["error"]["tipo"] == "KeyError"


# --- meal_plan_suggest ---------------------------------------------------------------------


def _escribir_recetas(vault_path) -> None:
    """Receta con ítem crítico (pollo) y receta sin ítems críticos."""
    escribir_md(
        vault_path,
        "recetas",
        "pollo-plancha.md",
        {
            "id": "recipe_pollo",
            "titulo": "Pollo a la plancha",
            "categoria": "comida",
            "tiempo_minutos": 20,
            "raciones": 2,
            "ingredientes": [
                {
                    "item_id": "item_pollo",
                    "nombre": "Pechuga de pollo",
                    "cantidad": 300,
                    "unidad": "gramos",
                }
            ],
        },
    )
    escribir_md(
        vault_path,
        "recetas",
        "arroz-blanco.md",
        {
            "id": "recipe_arroz",
            "titulo": "Arroz blanco",
            "categoria": "comida",
            "tiempo_minutos": 15,
            "raciones": 2,
            "ingredientes": [
                {
                    "item_id": "item_conc_01",
                    "nombre": "Arroz integral",
                    "cantidad": 150,
                    "unidad": "gramos",
                }
            ],
        },
    )


async def test_meal_plan_suggest_prioriza_caducidad(
    vault_poblado: VaultManager,
) -> None:
    """Ítem que caduca en 2 días empuja la receta que lo usa."""
    caduca_pronto = (date.today() + timedelta(days=2)).isoformat()
    escribir_md(
        vault_poblado.vault_path,
        "inventario/nevera",
        "pollo.md",
        {
            "id": "item_pollo",
            "nombre": "Pechuga de pollo",
            "categoria": "congelados",
            "ubicacion": "nevera",
            "stock_actual": 0.5,
            "stock_minimo": 0.0,
            "unidad": "kg",
            "fecha_caducidad_proxima": caduca_pronto,
        },
    )
    _escribir_recetas(vault_poblado.vault_path)
    ctx = ContextoHomeVault(
        vault=vault_poblado, sync=GoogleSync(vault_poblado), parser=None
    )

    resultado = await tool_meal_plan_suggest(ctx, prioritize_expiring=True)

    assert resultado["ok"] is True
    assert resultado["prioriza_caducidad"] is True
    # Solo la receta del pollo consume stock crítico
    assert len(resultado["sugerencias"]) == 1
    sugerencia = resultado["sugerencias"][0]
    assert sugerencia["receta_id"] == "recipe_pollo"
    assert sugerencia["consumo_critico_total"] == 300
    assert sugerencia["items_criticos_usados"][0]["item_id"] == "item_pollo"
    assert sugerencia["items_criticos_usados"][0]["dias_restantes"] == 2


async def test_meal_plan_suggest_sin_priorizar(
    vault_poblado: VaultManager,
) -> None:
    """Sin priorización devuelve todas las recetas."""
    _escribir_recetas(vault_poblado.vault_path)
    ctx = ContextoHomeVault(
        vault=vault_poblado, sync=GoogleSync(vault_poblado), parser=None
    )

    resultado = await tool_meal_plan_suggest(ctx, prioritize_expiring=False)

    assert resultado["ok"] is True
    assert {s["receta_id"] for s in resultado["sugerencias"]} == {
        "recipe_pollo",
        "recipe_arroz",
    }


# --- shopping_list_get_and_modify ----------------------------------------------------------


async def test_shopping_list_ciclo_completo(ctx: ContextoHomeVault) -> None:
    """add (dos veces, sin duplicar) -> get -> check -> remove -> get."""
    vacia = await tool_shopping_list_get_and_modify(ctx, "get")
    assert vacia["ok"] is True
    assert vacia["entradas"] == []

    # Ítem sin existencia en inventario: línea simple sin metadata
    anadido = await tool_shopping_list_get_and_modify(ctx, "add", "Detergente")
    assert anadido["ok"] is True
    assert anadido["anadido"] is True
    assert anadido["item_id"] is None

    duplicado = await tool_shopping_list_get_and_modify(ctx, "add", "Detergente")
    assert duplicado["anadido"] is False

    # Ítem existente: la línea lleva su item_id en la metadata
    existente = await tool_shopping_list_get_and_modify(ctx, "add", "Yogur")
    assert existente["anadido"] is True
    assert existente["item_id"] == "item_test_01"

    lista = await tool_shopping_list_get_and_modify(ctx, "get")
    assert len(lista["entradas"]) == 2
    assert all(not e["comprado"] for e in lista["entradas"])

    tachado = await tool_shopping_list_get_and_modify(ctx, "check", "Detergente")
    assert tachado["tachadas"] == 1
    lista = await tool_shopping_list_get_and_modify(ctx, "get")
    detergente = [
        e for e in lista["entradas"] if e["nombre"] == "Detergente"
    ][0]
    assert detergente["comprado"] is True

    eliminado = await tool_shopping_list_get_and_modify(
        ctx, "remove", "Detergente"
    )
    assert eliminado["eliminadas"] == 1
    lista = await tool_shopping_list_get_and_modify(ctx, "get")
    assert [e["nombre"] for e in lista["entradas"]] == ["Yogur natural"]


async def test_shopping_list_accion_invalida(ctx: ContextoHomeVault) -> None:
    """Acción desconocida o sin item_name devuelve error estructurado."""
    resultado = await tool_shopping_list_get_and_modify(ctx, "borrar", "x")
    assert resultado["ok"] is False
    assert resultado["error"]["tipo"] == "ValueError"

    sin_nombre = await tool_shopping_list_get_and_modify(ctx, "add")
    assert sin_nombre["ok"] is False


# --- Registro de herramientas en el servidor ---------------------------------------------


async def test_create_mcp_server_registra_las_7_herramientas(
    ctx: ContextoHomeVault,
) -> None:
    """El MCPServer expone exactamente las 7 herramientas del spec."""
    server = create_mcp_server(ctx)
    tools = await server.list_tools()
    nombres = {t.name for t in tools}
    assert nombres == {
        "inventory_record_purchase",
        "inventory_consume",
        "inventory_query_expiring",
        "task_list_pending",
        "task_mark_completed",
        "meal_plan_suggest",
        "shopping_list_get_and_modify",
    }
