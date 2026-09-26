"""Asistente conversacional del hogar: chat sobre el vault con LLM local.

Construye un contexto compacto del estado del hogar (inventario, caducidades,
lista de la compra, tareas y plan semanal) y lo inyecta en el prompt de un
cliente LLM inyectable (por defecto el Ollama local del homelab). El chat es
de solo lectura: no modifica el vault.
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.ai_vision_parser import ClienteLLM
from backend.models import PlanSemanal, RespuestaChat
from backend.vault_manager import VaultManager, ahora_utc

# Límites del contexto para no desbordar modelos locales pequeños
_MAX_ITEMS_CONTEXTO = 40
_MAX_TAREAS_CONTEXTO = 20

PROMPT_SISTEMA = """Eres el asistente del hogar de HomeVault AI, un sistema que \
gestiona el inventario, la lista de la compra, las tareas domésticas y el \
planificador de comidas de esta casa.

Reglas:
- Responde SIEMPRE en español, de forma clara, breve y directa (máximo 6 frases).
- Usa EXCLUSIVAMENTE la información del contexto del hogar que se te da abajo.
- Si el dato no está en el contexto, di simplemente que no tienes esa información.
- No inventes cifras, fechas ni productos. Puedes hacer cálculos sencillos con \
los datos del contexto (por ejemplo, qué recetas encajan con lo que hay).
- Si hay tareas VENCIDAS o productos que caducan en las próximas 48 horas, \
menciónalos siempre, aunque la pregunta sea sobre otra cosa.
- No propongas acciones que modifiquen datos; solo informa y sugiere.
"""


class HomeChat:
    """Chat de consulta sobre el estado del hogar."""

    def __init__(self, vault: VaultManager, llm: ClienteLLM) -> None:
        self._vault = vault
        self._llm = llm

    async def construir_contexto(self) -> tuple[str, int, int]:
        """Resumen textual del hogar. Devuelve (contexto, n_items, n_tareas)."""
        ahora = ahora_utc()
        hoy = ahora.date()

        items = await self._vault.list_items()
        expiring = await self._vault.query_expiring(7)
        entradas = await self._vault.get_shopping_list()
        tareas = await self._vault.list_tasks()

        lineas: list[str] = []

        items_con_stock = [i for i in items if i.stock_actual > 0][
            :_MAX_ITEMS_CONTEXTO
        ]
        lineas.append(f"## Inventario ({len(items)} ítems en total, mostrando los que tienen stock)")
        for item in items_con_stock:
            detalles = [f"{item.stock_actual:g} {item.unidad}"]
            detalles.append(f"ubicación: {item.ubicacion}")
            if item.categoria:
                detalles.append(f"categoría: {item.categoria}")
            if item.fecha_caducidad_proxima:
                detalles.append(f"caduca: {item.fecha_caducidad_proxima.isoformat()}")
            lineas.append(f"- {item.nombre}: " + ", ".join(detalles))
        if not items_con_stock:
            lineas.append("- (sin ítems con stock)")

        lineas.append("")
        lineas.append("## Caducidades próximas (7 días)")
        if expiring:
            for e in expiring:
                lineas.append(f"- {e.nombre}: en {e.dias_restantes} días ({e.fecha_caducidad.isoformat()})")
        else:
            lineas.append("- (ninguna)")

        lineas.append("")
        lineas.append("## Lista de la compra (pendiente)")
        pendientes = [e for e in entradas if not e.comprado]
        if pendientes:
            for e in pendientes:
                cantidad = f" ({e.cantidad:g} {e.unidad})" if e.cantidad else ""
                lineas.append(f"- {e.nombre}{cantidad}")
        else:
            lineas.append("- (vacía)")

        pendientes_tareas = [t for t in tareas if t.estado == "pendiente"]
        lineas.append("")
        lineas.append(f"## Tareas pendientes ({len(pendientes_tareas)})")
        for tarea in pendientes_tareas[:_MAX_TAREAS_CONTEXTO]:
            detalles = []
            if tarea.fecha_programada:
                estado = "VENCIDA" if tarea.fecha_programada < hoy else f"para {tarea.fecha_programada.isoformat()}"
                detalles.append(estado)
            detalles.append(f"prioridad: {tarea.prioridad}")
            if tarea.asignado_a:
                detalles.append(f"asignada a {tarea.asignado_a}")
            lineas.append(f"- {tarea.titulo} ({'; '.join(detalles)})")
        if not pendientes_tareas:
            lineas.append("- (ninguna)")

        plan = await self._plan_semana_actual(hoy)
        if plan is not None and plan.dias:
            lineas.append("")
            lineas.append("## Plan de comidas de esta semana")
            for dia in sorted(plan.dias.keys()):
                comidas = []
                for momento, comida in plan.dias[dia].items():
                    nombre = comida.plato_libre or comida.receta_id or "?"
                    comidas.append(f"{momento}: {nombre}")
                if comidas:
                    lineas.append(f"- {dia}: " + "; ".join(comidas))

        contexto = "\n".join(lineas)
        return contexto, len(items_con_stock), len(pendientes_tareas)

    async def _plan_semana_actual(self, hoy: date) -> PlanSemanal | None:
        """Lee el plan semanal de la semana ISO de ``hoy`` si existe."""
        semana = hoy.isocalendar()
        semana_iso = f"{semana.year}-W{semana.week:02d}"
        ruta = self._vault.vault_path / "planificador" / f"{semana_iso}.md"
        if not ruta.exists():
            return None
        try:
            plan, _ = await self._vault._read_doc(ruta, PlanSemanal)
            return plan
        except Exception:
            return None

    async def responder(self, mensaje: str) -> RespuestaChat:
        """Responde a una pregunta usando el contexto actual del hogar."""
        contexto, n_items, n_tareas = await self.construir_contexto()
        prompt = (
            f"{PROMPT_SISTEMA}\n\n"
            f"# Contexto del hogar\n{contexto}\n\n"
            f"# Pregunta\n{mensaje}\n\n"
            f"# Respuesta (en español, breve):"
        )
        respuesta = await self._llm.completar(prompt)
        return RespuestaChat(
            respuesta=respuesta.strip(),
            items_en_contexto=n_items,
            tareas_en_contexto=n_tareas,
        )
