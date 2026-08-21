"""Servidor MCP estándar de HomeVault AI (Fase 3).

Expone el vault Markdown como herramientas del Model Context Protocol
(transporte stdio) usando el SDK oficial `mcp`. Toda la lógica vive en las
funciones async `tool_*`, independientes del transporte e invocables
directamente desde los tests; el MCPServer solo las envuelve y serializa
su dict resultado a JSON.

Lanzamiento standalone: `python -m backend.mcp_server` (stdio), usando las
mismas settings de la aplicación (VAULT_PATH, AI_PROVIDER, etc.).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from mcp.server.mcpserver import MCPServer

from backend.ai_vision_parser import (
    ItemTicket,
    ReceiptParser,
    TicketParseado,
    build_llm_client,
    register_purchase,
)
from backend.config import Settings, get_settings
from backend.google_sync import GoogleSync, build_google_sync
from backend.vault_manager import VaultManager

logger = logging.getLogger(__name__)

# Ventana de caducidad (en días) que meal_plan_suggest considera crítica
DIAS_CRITICOS_CADUCIDAD = 4


@dataclass
class ContextoHomeVault:
    """Dependencias compartidas por las herramientas MCP."""

    vault: VaultManager
    sync: GoogleSync
    parser: Optional[ReceiptParser] = None  # None si no hay AI_PROVIDER


def _error(exc: Exception) -> dict:
    """Estructura de error uniforme de las herramientas MCP."""
    return {
        "ok": False,
        "error": {"tipo": type(exc).__name__, "mensaje": str(exc)},
    }


# --- Lógica de las herramientas (testeable sin transporte) ------------------------


async def tool_inventory_record_purchase(
    ctx: ContextoHomeVault,
    text_or_items: str | list[dict],
    store_name: str = "",
    total_cost: float = 0.0,
) -> dict:
    """Procesa una compra e incrementa inventario y finanzas.

    Si text_or_items es texto libre, se pasa por el ReceiptParser (LLM);
    si es una lista de ítems estructurada, se registra directamente.
    """
    try:
        if isinstance(text_or_items, str):
            if ctx.parser is None:
                raise RuntimeError(
                    "No hay proveedor de IA configurado (AI_PROVIDER); "
                    "pasa una lista de ítems estructurada en su lugar"
                )
            ticket = await ctx.parser.parse_ticket_from_text(
                text_or_items,
                comercio=store_name or None,
                total=total_cost or None,
            )
        else:
            ticket = TicketParseado(
                comercio=store_name or "Desconocido",
                total_ticket=total_cost,
                items=[ItemTicket.model_validate(i) for i in text_or_items],
            )
        resultado = await register_purchase(ctx.vault, ticket)
        return {"ok": True, **resultado.model_dump(mode="json")}
    except Exception as exc:
        logger.exception("Error en inventory_record_purchase")
        return _error(exc)


async def tool_inventory_consume(
    ctx: ContextoHomeVault,
    item_id_or_name: str,
    quantity: float,
    unit: str = "unidades",
) -> dict:
    """Consume unidades de un ítem (resolución id -> EAN -> nombre)."""
    try:
        item = await ctx.vault.resolve_item(item_id_or_name)
        if item is None:
            raise KeyError(f"Ítem no encontrado: {item_id_or_name}")
        resultado = await ctx.vault.consume_item(item.id, quantity)
        aviso_unidad = None
        if unit != item.unidad:
            aviso_unidad = (
                f"La unidad indicada ({unit}) difiere de la registrada "
                f"para el ítem ({item.unidad})"
            )
        return {
            "ok": True,
            **resultado.model_dump(mode="json"),
            "alerta_stock_minimo": resultado.bajo_minimo,
            "aviso_unidad": aviso_unidad,
        }
    except Exception as exc:
        logger.exception("Error en inventory_consume")
        return _error(exc)


async def tool_inventory_query_expiring(
    ctx: ContextoHomeVault, days_ahead: int = 4
) -> dict:
    """Lista los alimentos en riesgo de caducidad dentro de days_ahead."""
    try:
        items = await ctx.vault.query_expiring(days_ahead)
        return {
            "ok": True,
            "days_ahead": days_ahead,
            "items": [i.model_dump(mode="json") for i in items],
        }
    except Exception as exc:
        logger.exception("Error en inventory_query_expiring")
        return _error(exc)


async def tool_task_list_pending(
    ctx: ContextoHomeVault, assigned_user: Optional[str] = None
) -> dict:
    """Tareas pendientes del vault, con filtro opcional por usuario."""
    try:
        tareas = await ctx.vault.list_tasks(
            estado="pendiente", asignado_a=assigned_user
        )
        return {
            "ok": True,
            "tareas": [t.model_dump(mode="json") for t in tareas],
        }
    except Exception as exc:
        logger.exception("Error en task_list_pending")
        return _error(exc)


async def tool_task_mark_completed(
    ctx: ContextoHomeVault,
    task_id: str,
    completed_by: Optional[str] = None,
) -> dict:
    """Completa una tarea con el flujo completo de GoogleSync.

    Ejecuta primero la verificación de consumibles (marca bloqueada_por_stock
    y rellena la lista de la compra si falta stock) y después complete_task
    (historial, rotación, reprogramación y sync remoto si hay clientes).
    """
    try:
        verificada = await ctx.sync.check_consumables_before_task(task_id)
        tarea = await ctx.sync.complete_task(task_id, completed_by)
        return {
            "ok": True,
            "bloqueada_por_stock": verificada.bloqueada_por_stock,
            "tarea": tarea.model_dump(mode="json"),
        }
    except Exception as exc:
        logger.exception("Error en task_mark_completed")
        return _error(exc)


async def tool_meal_plan_suggest(
    ctx: ContextoHomeVault, prioritize_expiring: bool = True
) -> dict:
    """Sugiere menú a partir de las recetas del vault.

    Con prioritize_expiring activo, cruza los ítems que caducan en
    <= DIAS_CRITICOS_CADUCIDAD días contra las recetas que los usan y las
    ordena por cuánto stock crítico consumen (suma de cantidades).
    """
    try:
        recetas = await ctx.vault.list_recipes()
        if not prioritize_expiring:
            sugerencias = [
                {
                    "receta_id": r.id,
                    "titulo": r.titulo,
                    "categoria": r.categoria,
                    "tiempo_minutos": r.tiempo_minutos,
                    "items_criticos_usados": [],
                    "consumo_critico_total": 0.0,
                }
                for r in sorted(recetas, key=lambda r: r.titulo)
            ]
            return {
                "ok": True,
                "prioriza_caducidad": False,
                "sugerencias": sugerencias,
            }

        criticos = {
            c.item_id: c
            for c in await ctx.vault.query_expiring(DIAS_CRITICOS_CADUCIDAD)
        }
        sugerencias = []
        for receta in recetas:
            usados = [
                ing
                for ing in receta.ingredientes
                if ing.item_id in criticos
            ]
            if not usados:
                continue
            sugerencias.append(
                {
                    "receta_id": receta.id,
                    "titulo": receta.titulo,
                    "categoria": receta.categoria,
                    "tiempo_minutos": receta.tiempo_minutos,
                    "items_criticos_usados": [
                        {
                            "item_id": ing.item_id,
                            "nombre": ing.nombre,
                            "cantidad": ing.cantidad,
                            "unidad": ing.unidad,
                            "dias_restantes": criticos[
                                ing.item_id
                            ].dias_restantes,
                        }
                        for ing in usados
                    ],
                    "consumo_critico_total": round(
                        sum(ing.cantidad for ing in usados), 6
                    ),
                }
            )
        sugerencias.sort(
            key=lambda s: s["consumo_critico_total"], reverse=True
        )
        return {
            "ok": True,
            "prioriza_caducidad": True,
            "dias_criticos": DIAS_CRITICOS_CADUCIDAD,
            "sugerencias": sugerencias,
        }
    except Exception as exc:
        logger.exception("Error en meal_plan_suggest")
        return _error(exc)


async def tool_shopping_list_get_and_modify(
    ctx: ContextoHomeVault,
    action: str = "get",
    item_name: Optional[str] = None,
) -> dict:
    """Consulta o modifica listas/compra.md (action: get|add|remove|check)."""
    try:
        accion = action.strip().lower()
        if accion == "get":
            entradas = await ctx.vault.get_shopping_list()
            return {
                "ok": True,
                "accion": "get",
                "entradas": [e.model_dump(mode="json") for e in entradas],
            }
        if not item_name:
            raise ValueError(
                "item_name es obligatorio para las acciones add/remove/check"
            )
        if accion == "add":
            item = await ctx.vault.resolve_item(item_name)
            if item is not None:
                anadido = await ctx.vault.add_shopping_list_entry(
                    item.nombre,
                    item_id=item.id,
                    unidad=item.unidad,
                    categoria=item.categoria,
                )
                item_id = item.id
            else:
                anadido = await ctx.vault.add_shopping_list_entry(item_name)
                item_id = None
            return {
                "ok": True,
                "accion": "add",
                "anadido": anadido,
                "item_id": item_id,
            }
        if accion == "remove":
            eliminadas = await ctx.vault.remove_shopping_list_entry(item_name)
            return {"ok": True, "accion": "remove", "eliminadas": eliminadas}
        if accion == "check":
            tachadas = await ctx.vault.check_shopping_list_entry(item_name)
            return {"ok": True, "accion": "check", "tachadas": tachadas}
        raise ValueError(
            f"Acción no soportada: {action!r} (get|add|remove|check)"
        )
    except Exception as exc:
        logger.exception("Error en shopping_list_get_and_modify")
        return _error(exc)


# --- Servidor MCP (envoltura de transporte) ---------------------------------------


def _serializar(resultado: dict) -> str:
    """Serializa el dict resultado de una herramienta a JSON."""
    return json.dumps(resultado, ensure_ascii=False, default=str)


def create_mcp_server(ctx: ContextoHomeVault) -> MCPServer:
    """Crea el MCPServer con las 7 herramientas sobre el contexto dado."""
    server = MCPServer(name="homevault-ai", version="0.3.0")

    @server.tool(
        name="inventory_record_purchase",
        description=(
            "Procesa una compra (texto libre vía LLM o lista de ítems "
            "estructurada): incrementa inventario y registra el gasto mensual"
        ),
    )
    async def inventory_record_purchase(
        text_or_items: str | list[dict],
        store_name: str = "",
        total_cost: float = 0.0,
    ) -> str:
        return _serializar(
            await tool_inventory_record_purchase(
                ctx, text_or_items, store_name, total_cost
            )
        )

    @server.tool(
        name="inventory_consume",
        description=(
            "Consume unidades de un ítem del inventario (id, EAN o nombre); "
            "devuelve el stock restante y alerta si tocó el mínimo"
        ),
    )
    async def inventory_consume(
        item_id_or_name: str, quantity: float, unit: str = "unidades"
    ) -> str:
        return _serializar(
            await tool_inventory_consume(ctx, item_id_or_name, quantity, unit)
        )

    @server.tool(
        name="inventory_query_expiring",
        description="Lista los alimentos en riesgo de caducidad",
    )
    async def inventory_query_expiring(days_ahead: int = 4) -> str:
        return _serializar(await tool_inventory_query_expiring(ctx, days_ahead))

    @server.tool(
        name="task_list_pending",
        description="Lista las tareas domésticas pendientes, filtrables por usuario",
    )
    async def task_list_pending(assigned_user: Optional[str] = None) -> str:
        return _serializar(await tool_task_list_pending(ctx, assigned_user))

    @server.tool(
        name="task_mark_completed",
        description=(
            "Marca una tarea como completada: verificación previa de "
            "consumibles, historial, rotación y reprogramación"
        ),
    )
    async def task_mark_completed(
        task_id: str, completed_by: Optional[str] = None
    ) -> str:
        return _serializar(
            await tool_task_mark_completed(ctx, task_id, completed_by)
        )

    @server.tool(
        name="meal_plan_suggest",
        description=(
            "Sugiere menú; con prioritize_expiring cruza las caducidades "
            "próximas contra las recetas que consumen ese stock crítico"
        ),
    )
    async def meal_plan_suggest(prioritize_expiring: bool = True) -> str:
        return _serializar(
            await tool_meal_plan_suggest(ctx, prioritize_expiring)
        )

    @server.tool(
        name="shopping_list_get_and_modify",
        description=(
            "Consulta o modifica la lista de la compra "
            "(action: get|add|remove|check)"
        ),
    )
    async def shopping_list_get_and_modify(
        action: str = "get", item_name: Optional[str] = None
    ) -> str:
        return _serializar(
            await tool_shopping_list_get_and_modify(ctx, action, item_name)
        )

    return server


# --- Construcción del contexto y punto de entrada -----------------------------------


def build_context(settings: Settings) -> ContextoHomeVault:
    """Construye el contexto de las herramientas desde las settings.

    GoogleSync se crea con clientes reales solo si google_sync_enabled; en
    caso contrario (o si falla) se usa el fallback local sin sync remoto.
    El ReceiptParser solo se crea si hay ai_provider configurado.
    """
    vault = VaultManager(settings.vault_path)

    sync: Optional[GoogleSync] = None
    if settings.google_sync_enabled:
        try:
            sync = build_google_sync(vault, settings)
        except Exception:
            logger.exception(
                "No se pudo inicializar GoogleSync; MCP sigue solo con "
                "lógica local"
            )
    if sync is None:
        sync = GoogleSync(
            vault,
            tasks_list_id=settings.google_tasks_list_id,
            calendar_id=settings.google_calendar_id,
        )

    parser: Optional[ReceiptParser] = None
    if settings.ai_provider:
        try:
            parser = ReceiptParser(vault, build_llm_client(settings))
        except Exception:
            logger.exception("No se pudo inicializar el cliente LLM")

    return ContextoHomeVault(vault=vault, sync=sync, parser=parser)


def main() -> None:
    """Punto de entrada standalone: servidor MCP por stdio."""
    logging.basicConfig(level=logging.INFO)
    server = create_mcp_server(build_context(get_settings()))
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
