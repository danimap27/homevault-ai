"""Planificador inteligente de cocina (Fase 4c).

Tres operaciones sobre el vault Markdown como única fuente de verdad:

- rescue_chef: cruza los ítems próximos a caducar con las recetas que los
  usan para sugerir qué cocinar antes de que se estropeen.
- batch_cooking: descuenta los ingredientes crudos del inventario (FIFO vía
  consume_item) y crea un .md de tupper por receta en inventario/<destino>/.
- modo_evento: escala las cantidades de las recetas por número de invitados
  y añade SOLO los faltantes a listas/compra.md.

Toda la E/S pasa por el VaultManager inyectado, por lo que los tests usan un
vault temporal sin tocar el real.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from datetime import date, timedelta
from typing import Optional, get_args

from pydantic import BaseModel, Field

from backend.models import (
    ComidaPlanificada,
    Consumible,
    Ingrediente,
    IngredienteFaltante,
    ItemCaducidad,
    PlanSemanal,
    Receta,
    RecetaPosible,
    Ubicacion,
)

from backend.vault_manager import VaultManager, ahora_utc

logger = logging.getLogger(__name__)

# Ubicaciones válidas derivadas del Literal del modelo de Fase 1
UBICACIONES_VALIDAS: frozenset[str] = frozenset(get_args(Ubicacion))

# Vida por defecto de un tupper congelado si no se indica otra cosa
DIAS_MAX_CONGELADOR_DEFECTO = 90


def _slugificar(texto: str) -> str:
    """Slug ASCII snake_case a partir de un título libre."""
    normalizado = unicodedata.normalize("NFKD", texto)
    ascii_str = normalizado.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_str.lower()).strip("_")
    return slug or "tupper"


# --- Modelos de resultado ------------------------------------------------------


class SugerenciaRescate(BaseModel):
    """Receta sugerida por el Rescue Chef con los ítems que rescata."""

    receta: Receta
    items_a_rescatar: list[ItemCaducidad] = Field(default_factory=list)
    dias_restantes_min: int
    stock_critico: bool = False


class IngredienteBatch(BaseModel):
    """Resultado del descuento de un ingrediente en el batch cooking."""

    item_id: Optional[str] = None
    nombre: str
    cantidad: float
    unidad: str
    consumido: bool = False
    detalle: str = ""


class TupperCreado(BaseModel):
    """Tupper generado en inventario/<destino>/ tras cocinar una receta."""

    receta_id: str
    titulo: str
    item_id: str
    ruta: str  # relativa a la raíz del vault
    raciones: int
    fecha_congelacion: date
    fecha_caducidad: date


class ResultadoBatchCooking(BaseModel):
    """Resultado agregado de batch_cooking()."""

    destino: str
    tuppers: list[TupperCreado] = Field(default_factory=list)
    ingredientes: list[IngredienteBatch] = Field(default_factory=list)


class FaltanteEvento(BaseModel):
    """Ingrediente escalado de un evento y su cobertura contra stock."""

    receta_id: str
    item_id: Optional[str] = None
    nombre: str
    unidad: str
    cantidad_necesaria: float
    stock_disponible: float
    faltante: float
    anadido_a_lista: bool = False


class ResultadoEvento(BaseModel):
    """Resultado agregado de modo_evento()."""

    invitados: int
    faltantes: list[FaltanteEvento] = Field(default_factory=list)


class IngredienteConsumido(BaseModel):
    """Ingrediente descontado del inventario al cocinar una receta."""

    item_id: str
    nombre: str
    cantidad: float
    unidad: str
    stock_actual: float


class ResultadoCocinarReceta(BaseModel):
    """Resultado de cocinar una receta consumiendo sus ingredientes."""

    consumidos: list[IngredienteConsumido] = Field(default_factory=list)
    faltantes: list[IngredienteFaltante] = Field(default_factory=list)


class ResultadoAsignarPlan(BaseModel):
    """Resultado de asignar una receta a un slot del planificador semanal."""

    plan: PlanSemanal
    faltantes_anadidos: list[IngredienteFaltante] = Field(
        default_factory=list
    )


class InsufficientStockError(Exception):
    """Faltan ingredientes en inventario para cocinar una receta."""

    def __init__(self, faltantes: list[IngredienteFaltante]) -> None:
        self.faltantes = faltantes
        super().__init__("Stock insuficiente para cocinar la receta")


# --- Lógica de negocio ----------------------------------------------------------


class Planner:
    """Planificador de cocina apoyado en el VaultManager inyectado."""

    def __init__(self, vault: VaultManager) -> None:
        self._vault = vault

    async def _mapa_recetas(self) -> dict[str, Receta]:
        """Devuelve las recetas del vault indexadas por id."""
        return {r.id: r for r in await self._vault.list_recipes()}

    # --- Rescue Chef -----------------------------------------------------------

    async def rescue_chef(self, dias: int = 4) -> list[SugerenciaRescate]:
        """Recetas que usan ítems que caducan en <= `dias` días.

        Ordenación por criticidad del stock que consumen: primero las recetas
        cuyo ingrediente más urgente caduca antes; a igual urgencia, las que
        rescatan más ítems. `stock_critico` marca las recetas que consumen
        algún ítem además bajo mínimo de stock.
        """
        por_caducar = await self._vault.query_expiring(dias)
        if not por_caducar:
            return []
        caducidad_por_item = {c.item_id: c for c in por_caducar}

        sugerencias: list[SugerenciaRescate] = []
        for receta in await self._vault.list_recipes():
            usados = [
                caducidad_por_item[ing.item_id]
                for ing in receta.ingredientes
                if ing.item_id and ing.item_id in caducidad_por_item
            ]
            if not usados:
                continue
            critico = False
            for item_cad in usados:
                item = await self._vault.get_item(item_cad.item_id)
                if item and item.stock_actual <= item.stock_minimo:
                    critico = True
                    break
            sugerencias.append(
                SugerenciaRescate(
                    receta=receta,
                    items_a_rescatar=sorted(
                        usados, key=lambda c: c.fecha_caducidad
                    ),
                    dias_restantes_min=min(c.dias_restantes for c in usados),
                    stock_critico=critico,
                )
            )
        # Más urgente primero; a igual urgencia, la que más ítems rescata
        sugerencias.sort(
            key=lambda s: (s.dias_restantes_min, -len(s.items_a_rescatar))
        )
        return sugerencias

    # --- Batch cooking -----------------------------------------------------------

    async def batch_cooking(
        self,
        receta_ids: list[str],
        destino: str = "congelador",
        dias_max_congelador: Optional[int] = None,
    ) -> ResultadoBatchCooking:
        """Cocina en lote: descuenta crudos del inventario y crea tuppers.

        Por cada receta se consumen sus ingredientes vía consume_item (FIFO)
        y se crea un .md de tupper en inventario/<destino>/ con el esquema
        Consumible (categoria congelados, unidad unidades, fecha_congelacion
        hoy y caducidad hoy + dias_max_congelador o +90 días por defecto).

        Raises:
            ValueError: si `destino` no es una ubicación válida del esquema.
            KeyError: si alguna receta no existe en el vault.
        """
        if destino not in UBICACIONES_VALIDAS:
            raise ValueError(f"Destino de inventario no válido: {destino}")
        dias_vida = dias_max_congelador or DIAS_MAX_CONGELADOR_DEFECTO
        recetas = await self._mapa_recetas()
        hoy = ahora_utc().date()

        resultado = ResultadoBatchCooking(destino=destino)
        for receta_id in receta_ids:
            receta = recetas.get(receta_id)
            if receta is None:
                raise KeyError(f"Receta no encontrada: {receta_id}")

            for ing in receta.ingredientes:
                resultado.ingredientes.append(
                    await self._consumir_ingrediente(ing)
                )

            tupper = await self._crear_tupper(receta, destino, hoy, dias_vida)
            resultado.tuppers.append(tupper)
            logger.info(
                "Tupper creado: %s (%s) en %s",
                tupper.item_id,
                receta.titulo,
                tupper.ruta,
            )
        return resultado

    async def _consumir_ingrediente(self, ing: Ingrediente) -> IngredienteBatch:
        """Descuenta un ingrediente del inventario (si tiene item_id)."""
        if not ing.item_id:
            return IngredienteBatch(
                nombre=ing.nombre,
                cantidad=ing.cantidad,
                unidad=ing.unidad,
                consumido=False,
                detalle="sin item_id: no vinculado al inventario",
            )
        if await self._vault.get_item(ing.item_id) is None:
            return IngredienteBatch(
                item_id=ing.item_id,
                nombre=ing.nombre,
                cantidad=ing.cantidad,
                unidad=ing.unidad,
                consumido=False,
                detalle="ítem no encontrado en el inventario",
            )
        consumo = await self._vault.consume_item(ing.item_id, ing.cantidad)
        return IngredienteBatch(
            item_id=ing.item_id,
            nombre=ing.nombre,
            cantidad=ing.cantidad,
            unidad=ing.unidad,
            consumido=True,
            detalle=f"stock restante: {consumo.stock_actual}",
        )

    async def _crear_tupper(
        self, receta: Receta, destino: str, hoy: date, dias_vida: int
    ) -> TupperCreado:
        """Crea el .md del tupper con el esquema Consumible de Fase 1."""
        slug = _slugificar(receta.titulo)
        item_id = f"tupper_{slug}_{hoy:%Y%m%d}"
        if await self._vault.get_item(item_id) is not None:
            item_id = f"{item_id}_{uuid.uuid4().hex[:6]}"

        caducidad = hoy + timedelta(days=dias_vida)
        tupper = Consumible(
            id=item_id,
            nombre=f"{receta.titulo} (tupper {hoy.isoformat()})",
            categoria="congelados",
            ubicacion=destino,  # validado contra UBICACIONES_VALIDAS
            stock_actual=float(receta.raciones),
            stock_minimo=0.0,
            unidad="unidades",
            fecha_caducidad_proxima=caducidad,
            fecha_congelacion=hoy,
            dias_max_congelador=dias_vida,
            lotes=[],
            tags=["batch-cooking", receta.id],
            ultima_actualizacion=ahora_utc(),
        )
        ruta = self._vault.vault_path / "inventario" / destino / f"{item_id}.md"
        cuerpo = (
            f"# {receta.titulo} (tupper)\n\n"
            f"Batch cooking del {hoy.isoformat()}.\n\n"
            f"- Receta origen: `{receta.id}`\n"
            f"- Raciones: {receta.raciones}\n"
            f"- Consumar antes de: {caducidad.isoformat()}\n"
        )
        await self._vault._write_doc(ruta, tupper, cuerpo)
        return TupperCreado(
            receta_id=receta.id,
            titulo=receta.titulo,
            item_id=item_id,
            ruta=str(ruta.relative_to(self._vault.vault_path)),
            raciones=receta.raciones,
            fecha_congelacion=hoy,
            fecha_caducidad=caducidad,
        )

    # --- Modo evento ---------------------------------------------------------------

    async def modo_evento(
        self, receta_ids: list[str], invitados: int
    ) -> ResultadoEvento:
        """Escala recetas por invitados y lista SOLO los faltantes.

        cantidad_necesaria = cantidad * (invitados / raciones). El faltante
        es max(0, necesaria - stock_actual); solo los faltantes positivos se
        añaden a listas/compra.md (add_shopping_list_entry ya evita
        duplicados de líneas pendientes).

        Raises:
            ValueError: si invitados < 1.
            KeyError: si alguna receta no existe en el vault.
        """
        if invitados < 1:
            raise ValueError("invitados debe ser >= 1")
        recetas = await self._mapa_recetas()

        resultado = ResultadoEvento(invitados=invitados)
        for receta_id in receta_ids:
            receta = recetas.get(receta_id)
            if receta is None:
                raise KeyError(f"Receta no encontrada: {receta_id}")
            factor = invitados / receta.raciones

            for ing in receta.ingredientes:
                necesaria = round(ing.cantidad * factor, 2)
                disponible = 0.0
                categoria: Optional[str] = None
                if ing.item_id:
                    item = await self._vault.get_item(ing.item_id)
                    if item is not None:
                        disponible = item.stock_actual
                        categoria = item.categoria
                faltante = round(max(necesaria - disponible, 0.0), 2)

                anadido = False
                if faltante > 0:
                    anadido = await self._vault.add_shopping_list_entry(
                        ing.nombre,
                        item_id=ing.item_id,
                        cantidad=faltante,
                        unidad=ing.unidad,
                        categoria=categoria,
                    )
                resultado.faltantes.append(
                    FaltanteEvento(
                        receta_id=receta.id,
                        item_id=ing.item_id,
                        nombre=ing.nombre,
                        unidad=ing.unidad,
                        cantidad_necesaria=necesaria,
                        stock_disponible=disponible,
                        faltante=faltante,
                        anadido_a_lista=anadido,
                    )
                )
        return resultado

    # --- "¿Qué recetas puedo hacer?" --------------------------------------------

    async def _calcular_faltantes(
        self, receta: Receta, raciones: int
    ) -> list[IngredienteFaltante]:
        """Calcula los ingredientes vinculados que faltan para ``raciones``.

        Devuelve solo faltantes positivos con la cantidad necesaria de compra.
        """
        if receta.raciones <= 0:
            raise ValueError("La receta debe tener raciones > 0")
        factor = raciones / receta.raciones
        faltantes: list[IngredienteFaltante] = []

        for ing in receta.ingredientes:
            if not ing.item_id:
                continue
            cantidad_necesaria = round(ing.cantidad * factor, 6)
            item = await self._vault.get_item(ing.item_id)
            disponible = item.stock_actual if item is not None else 0.0
            cantidad_faltante = round(max(cantidad_necesaria - disponible, 0.0), 6)
            if cantidad_faltante > 0:
                faltantes.append(
                    IngredienteFaltante(
                        item_id=ing.item_id,
                        nombre=ing.nombre,
                        cantidad=cantidad_faltante,
                        unidad=ing.unidad,
                    )
                )
        return faltantes

    async def possible_recipes(self) -> list[RecetaPosible]:
        """Recetas ordenadas por completitud respecto al inventario actual.

        El score es la proporción de ingredientes con ``item_id`` que tienen
        stock suficiente. En empate gana la receta con menos cantidad faltante.
        Las recetas sin ingredientes vinculados obtienen score 1.0.
        """
        recetas = await self._vault.list_recipes()
        resultado: list[RecetaPosible] = []

        for receta in recetas:
            ingredientes_con_item = [
                ing for ing in receta.ingredientes if ing.item_id
            ]
            total_con_item = len(ingredientes_con_item)

            satisfechos = 0
            for ing in ingredientes_con_item:
                item = await self._vault.get_item(ing.item_id)
                if item is not None and item.stock_actual >= ing.cantidad:
                    satisfechos += 1

            faltantes = await self._calcular_faltantes(receta, receta.raciones)
            if total_con_item > 0:
                score = round(satisfechos / total_con_item, 4)
            else:
                score = 1.0

            resultado.append(
                RecetaPosible(
                    receta=receta,
                    ingredientes_satisfechos=satisfechos,
                    ingredientes_faltantes=total_con_item - satisfechos,
                    score=score,
                    faltantes_para_compra=faltantes,
                )
            )

        resultado.sort(
            key=lambda r: (-r.score, sum(f.cantidad for f in r.faltantes_para_compra))
        )
        return resultado

    async def cook_recipe(
        self, receta_id: str, raciones: int | None = None
    ) -> ResultadoCocinarReceta:
        """Consume del inventario los ingredientes de una receta.

        El comportamiento es transaccional: se prechequea el stock de todos
        los ingredientes vinculados. Si falta alguno no se consume nada y se
        lanza ``InsufficientStockError`` con el listado de faltantes.

        Args:
            receta_id: identificador de la receta.
            raciones: porciones a cocinar. Por defecto las de la receta.

        Raises:
            KeyError: si la receta no existe.
            ValueError: si ``raciones`` es menor que 1.
            InsufficientStockError: si falta stock para algún ingrediente.
        """
        receta = await self._vault.get_receta(receta_id)
        if receta is None:
            raise KeyError(f"Receta no encontrada: {receta_id}")

        raciones = raciones if raciones is not None else receta.raciones
        if raciones < 1:
            raise ValueError("raciones debe ser >= 1")

        faltantes = await self._calcular_faltantes(receta, raciones)
        if faltantes:
            raise InsufficientStockError(faltantes)

        factor = raciones / receta.raciones
        consumidos: list[IngredienteConsumido] = []
        for ing in receta.ingredientes:
            if not ing.item_id:
                continue
            cantidad = round(ing.cantidad * factor, 6)
            resultado = await self._vault.consume_item(ing.item_id, cantidad)
            consumidos.append(
                IngredienteConsumido(
                    item_id=ing.item_id,
                    nombre=ing.nombre,
                    cantidad=cantidad,
                    unidad=ing.unidad,
                    stock_actual=resultado.stock_actual,
                )
            )

        return ResultadoCocinarReceta(consumidos=consumidos, faltantes=[])

    # --- Planificación semanal --------------------------------------------------

    async def assign_recipe_to_plan(
        self,
        semana_iso: str,
        dia: str,
        toma: str,
        receta_id: str,
        raciones: int,
    ) -> ResultadoAsignarPlan:
        """Asigna una receta a un slot del planificador y lista los faltantes.

        Crea el archivo ``planificador/<semana_iso>.md`` si no existe, calcula
        los ingredientes faltantes para las raciones indicadas y los añade a
        ``listas/compra.md``.

        Raises:
            KeyError: si la receta no existe.
            ValueError: si la semana ISO, el día o la toma no son válidos.
        """
        receta = await self._vault.get_receta(receta_id)
        if receta is None:
            raise KeyError(f"Receta no encontrada: {receta_id}")

        if raciones < 1:
            raise ValueError("raciones debe ser >= 1")

        try:
            anio_str, semana_str = semana_iso.split("-W")
            anio = int(anio_str)
            semana = int(semana_str)
            fecha_inicio = date.fromisocalendar(anio, semana, 1)
            fecha_fin = date.fromisocalendar(anio, semana, 7)
        except ValueError as exc:
            raise ValueError(
                f"Semana ISO inválida (formato YYYY-Www): {semana_iso}"
            ) from exc

        dias_validos = [
            "lunes",
            "martes",
            "miercoles",
            "jueves",
            "viernes",
            "sabado",
            "domingo",
        ]
        if dia not in dias_validos:
            raise ValueError(f"Día no válido: {dia}")
        if toma not in ("comida", "cena"):
            raise ValueError(f"Toma no válida: {toma}")

        ruta = self._vault.vault_path / "planificador" / f"{semana_iso}.md"
        lock = await self._vault._get_lock(ruta)
        async with lock:
            if ruta.exists():
                plan, cuerpo = await self._vault._read_doc(ruta, PlanSemanal)
            else:
                plan = PlanSemanal(
                    semana_iso=semana_iso,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                )
                cuerpo = f"# Semana {semana_iso}\n"

            if dia not in plan.dias:
                plan.dias[dia] = {}
            plan.dias[dia][toma] = ComidaPlanificada(
                receta_id=receta_id,
                raciones=raciones,
                stock_deducido=False,
            )
            await self._vault._write_doc(ruta, plan, cuerpo)

        faltantes = await self._calcular_faltantes(receta, raciones)
        anadidos: list[IngredienteFaltante] = []
        for faltante in faltantes:
            item = await self._vault.get_item(faltante.item_id)
            categoria = item.categoria if item is not None else None
            anadido = await self._vault.add_shopping_list_entry(
                nombre=faltante.nombre,
                item_id=faltante.item_id,
                cantidad=faltante.cantidad,
                unidad=faltante.unidad,
                categoria=categoria,
            )
            if anadido:
                anadidos.append(faltante)

        return ResultadoAsignarPlan(plan=plan, faltantes_anadidos=anadidos)
