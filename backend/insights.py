"""Motor de inteligencia de HomeVault AI.

Funciones puras (sin I/O) que convierten el estado del vault en decisiones:

- Predicciones de agotamiento a partir del ritmo real de consumo registrado
  en ``historial_consumo``.
- Sugerencias de reposición priorizadas para la lista de la compra.
- Valor económico del inventario.
- Estadísticas de tareas con reparto de equidad entre convivientes.

Nota sobre el stock: ``stock_actual`` es la cifra de referencia del sistema
(la que ve el usuario y la que dispara el mínimo); los lotes son el desglose
FIFO con caducidad de *parte* de ese stock, por lo que NO se suman para
calcular disponibilidad y así evitar doble conteo.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from math import ceil
from typing import Iterable, Literal, Optional, Sequence

from backend.models import (
    Consumible,
    CuotaConviviente,
    EstadisticasTareas,
    EntradaListaCompra,
    PrediccionAgotamiento,
    SugerenciaReposicion,
    Tarea,
    TareaVencida,
)

# --- Parámetros del motor -----------------------------------------------------

VENTANA_TASA_DIAS = 45  # ventana de historial usada para estimar el ritmo
MIN_CONSUMOS_TASA = 2  # consumos mínimos para estimar una tasa
MIN_DIAS_OBSERVACION = 7.0  # días mínimos de observación (estabiliza tasas)

HORIZONTE_REPOSICION_DIAS = 14  # horizonte para sugerir reposición
UMBRAL_CRITICO_DIAS = 3.0
UMBRAL_ALTA_DIAS = 7.0

_MAX_HISTORIAL = 100  # entradas máximas conservadas por ítem
_PODA_HISTORIAL_DIAS = 365


def ahora_utc() -> datetime:
    """Ahora en UTC (los timestamps del vault se guardan en UTC)."""
    return datetime.now(timezone.utc)


def disponible_total(item: Consumible) -> float:
    """Stock de referencia de un ítem (sin sumar lotes, ver nota del módulo)."""
    return round(item.stock_actual, 6)


# --- Predicciones de agotamiento ----------------------------------------------


def _historial_en_ventana(
    item: Consumible, ahora: datetime, ventana_dias: int = VENTANA_TASA_DIAS
) -> list:
    """Consumos del historial dentro de la ventana, ordenados por fecha."""
    desde = ahora - timedelta(days=ventana_dias)
    consumos = [c for c in item.historial_consumo if c.fecha >= desde]
    return sorted(consumos, key=lambda c: c.fecha)


def tasa_consumo_diaria(
    item: Consumible,
    *,
    ahora: Optional[datetime] = None,
    ventana_dias: int = VENTANA_TASA_DIAS,
) -> Optional[float]:
    """Unidades consumidas por día según el historial reciente.

    Usa los consumos de los últimos ``ventana_dias`` divididos entre los días
    transcurridos desde el primero de ellos (mínimo ``MIN_DIAS_OBSERVACION``).
    Devuelve ``None`` si no hay datos suficientes para estimar.
    """
    ahora = ahora or ahora_utc()
    consumos = _historial_en_ventana(item, ahora, ventana_dias)
    if len(consumos) < MIN_CONSUMOS_TASA:
        return None

    total = sum(c.cantidad for c in consumos)
    if total <= 0:
        return None

    dias_observados = (ahora - consumos[0].fecha).total_seconds() / 86400
    dias = max(dias_observados, MIN_DIAS_OBSERVACION)
    return total / dias


def _confianza_prediccion(
    consumos: Sequence, ahora: datetime
) -> Literal["alta", "media", "baja"]:
    """Confianza según volumen de datos: alta/media/baja."""
    if len(consumos) >= 5:
        dias_observados = (ahora - consumos[0].fecha).total_seconds() / 86400
        if dias_observados >= 21:
            return "alta"
        return "media"
    if len(consumos) >= 3:
        return "media"
    return "baja"


def predecir_agotamiento(
    item: Consumible, *, ahora: Optional[datetime] = None
) -> Optional[PrediccionAgotamiento]:
    """Proyecta cuándo se agotará un ítem. ``None`` si no hay base suficiente."""
    ahora = ahora or ahora_utc()
    disponible = disponible_total(item)
    if disponible <= 0:
        return None

    tasa = tasa_consumo_diaria(item, ahora=ahora)
    if tasa is None or tasa <= 0:
        return None

    dias_restantes = disponible / tasa
    consumos = _historial_en_ventana(item, ahora)
    fecha_estimada = (ahora + timedelta(days=ceil(dias_restantes))).date()

    return PrediccionAgotamiento(
        item_id=item.id,
        nombre=item.nombre,
        unidad=item.unidad,
        disponible=round(disponible, 3),
        tasa_diaria=round(tasa, 4),
        dias_restantes=round(dias_restantes, 1),
        fecha_estimada_agotamiento=fecha_estimada,
        confianza=_confianza_prediccion(consumos, ahora),
    )


def construir_predicciones(
    items: Iterable[Consumible],
    *,
    ahora: Optional[datetime] = None,
    limite: Optional[int] = None,
) -> list[PrediccionAgotamiento]:
    """Predicciones de todos los ítems con datos, ordenadas por urgencia."""
    ahora = ahora or ahora_utc()
    predicciones = [
        p
        for item in items
        if (p := predecir_agotamiento(item, ahora=ahora)) is not None
    ]
    predicciones.sort(key=lambda p: p.dias_restantes)
    if limite is not None:
        return predicciones[:limite]
    return predicciones


# --- Sugerencias de reposición ------------------------------------------------


def _normalizar(texto: str) -> str:
    return " ".join(texto.strip().lower().split())


def _ids_y_nombres_en_lista(
    entradas: Iterable[EntradaListaCompra],
) -> tuple[set[str], set[str]]:
    """Ids y nombres (normalizados) de entradas pendientes de la compra."""
    ids: set[str] = set()
    nombres: set[str] = set()
    for entrada in entradas:
        if entrada.comprado:
            continue
        ids.add(entrada.item_id)
        nombres.add(_normalizar(entrada.nombre))
    return ids, nombres


def _urgencia(
    disponible: float, dias_restantes: Optional[float]
) -> Literal["critica", "alta", "media"]:
    if disponible <= 0:
        return "critica"
    if dias_restantes is not None:
        if dias_restantes <= UMBRAL_CRITICO_DIAS:
            return "critica"
        if dias_restantes <= UMBRAL_ALTA_DIAS:
            return "alta"
        return "media"
    # Sin predicción: el hecho de estar por debajo del mínimo ya es señal alta
    return "alta"


def sugerencias_reposicion(
    items: Iterable[Consumible],
    entradas_lista: Sequence[EntradaListaCompra] = (),
    *,
    ahora: Optional[datetime] = None,
    horizonte_dias: int = HORIZONTE_REPOSICION_DIAS,
) -> list[SugerenciaReposicion]:
    """Ítems que conviene reponer, ordenados por urgencia y fecha de agotamiento.

    Un ítem entra en la lista si está agotado, por debajo de su mínimo, o si su
    predicción lo agota dentro del horizonte. Los que ya están en la lista de
    la compra se marcan con ``ya_en_lista`` (no se descartan, para poder
    mostrarlos como "pendiente de compra").
    """
    ahora = ahora or ahora_utc()
    ids_en_lista, nombres_en_lista = _ids_y_nombres_en_lista(entradas_lista)

    sugerencias: list[SugerenciaReposicion] = []
    for item in items:
        disponible = disponible_total(item)
        prediccion = predecir_agotamiento(item, ahora=ahora)
        dias = prediccion.dias_restantes if prediccion else None

        agotado = disponible <= 0
        bajo_minimo = item.stock_minimo > 0 and disponible <= item.stock_minimo
        se_agota_pronto = dias is not None and dias <= horizonte_dias
        if not (agotado or bajo_minimo or se_agota_pronto):
            continue

        # Un ítem que nunca se ha tenido ni consumido no es una reposición,
        # es un artículo pendiente de estrenar: se gestiona desde la lista.
        nunca_usado = (
            item.lotes == []
            and not item.historial_consumo
            and item.ultimo_consumo is None
        )
        if nunca_usado and not se_agota_pronto:
            continue

        motivos: list[str] = []
        if agotado:
            motivos.append("Sin stock")
        elif bajo_minimo:
            motivos.append(
                f"Por debajo del mínimo ({disponible:g} de {item.stock_minimo:g} {item.unidad})"
            )
        if se_agota_pronto and dias is not None:
            motivos.append(f"Se agota en ~{dias:g} días")

        ya_en_lista = item.id in ids_en_lista or _normalizar(item.nombre) in nombres_en_lista

        sugerencias.append(
            SugerenciaReposicion(
                item_id=item.id,
                nombre=item.nombre,
                categoria=item.categoria,
                ubicacion=item.ubicacion,
                unidad=item.unidad,
                disponible=disponible,
                stock_minimo=item.stock_minimo,
                dias_restantes=dias,
                urgencia=_urgencia(disponible, dias),
                motivo=" · ".join(motivos),
                ya_en_lista=ya_en_lista,
                precio_estimado=item.precio_unitario_estimado,
            )
        )

    orden = {"critica": 0, "alta": 1, "media": 2}
    sugerencias.sort(
        key=lambda s: (
            orden[s.urgencia],
            s.dias_restantes if s.dias_restantes is not None else 10**6,
            s.nombre.lower(),
        )
    )
    return sugerencias


# --- Valor del inventario -----------------------------------------------------


def valor_inventario(items: Iterable[Consumible]) -> float:
    """Valor estimado (€) de todo el inventario con precio conocido."""
    total = 0.0
    for item in items:
        if item.precio_unitario_estimado is None:
            continue
        total += disponible_total(item) * item.precio_unitario_estimado
    return round(total, 2)


def items_bajo_minimo(items: Iterable[Consumible]) -> int:
    """Nº de ítems agotados o por debajo de su stock mínimo."""
    cuenta = 0
    for item in items:
        disponible = disponible_total(item)
        if disponible <= 0 or (
            item.stock_minimo > 0 and disponible <= item.stock_minimo
        ):
            cuenta += 1
    return cuenta


# --- Estadísticas de tareas ---------------------------------------------------


def _mes_de(fecha: date) -> str:
    return f"{fecha.year:04d}-{fecha.month:02d}"


def estadisticas_tareas(
    tareas: Iterable[Tarea],
    *,
    ahora: Optional[datetime] = None,
    mes: Optional[str] = None,
) -> EstadisticasTareas:
    """Métricas de tareas: completadas del mes, equidad y vencidas."""
    ahora = ahora or ahora_utc()
    hoy = ahora.date()
    mes = mes or _mes_de(hoy)

    completadas_mes = 0
    por_usuario: dict[str, int] = defaultdict(int)
    completadas_30d = 0
    a_tiempo_30d = 0
    con_fecha_30d = 0

    hace_30d = hoy.toordinal() - 30  # comparación rápida en días ordinales

    pendientes = 0
    proximas_7 = 0
    vencidas: list[TareaVencida] = []

    for tarea in tareas:
        for registro in tarea.historial_completados:
            fecha = registro.fecha
            if _mes_de(fecha) == mes:
                completadas_mes += 1
                por_usuario[registro.usuario or "Sin asignar"] += 1

            if fecha.toordinal() >= hace_30d:
                completadas_30d += 1
                if tarea.fecha_programada is not None:
                    con_fecha_30d += 1
                    if fecha <= tarea.fecha_programada:
                        a_tiempo_30d += 1

        if tarea.estado != "pendiente":
            continue
        pendientes += 1
        if tarea.fecha_programada is not None:
            delta = (tarea.fecha_programada - hoy).days
            if delta < 0:
                vencidas.append(
                    TareaVencida(
                        task_id=tarea.id,
                        titulo=tarea.titulo,
                        fecha_programada=tarea.fecha_programada,
                        dias_retraso=-delta,
                        asignado_a=tarea.asignado_a,
                        prioridad=tarea.prioridad,
                    )
                )
            elif delta <= 7:
                proximas_7 += 1

    total_mes = sum(por_usuario.values())
    cuotas = [
        CuotaConviviente(
            nombre=usuario,
            completadas=cuenta,
            porcentaje=round(100 * cuenta / total_mes, 1) if total_mes else 0.0,
        )
        for usuario, cuenta in sorted(
            por_usuario.items(), key=lambda kv: (-kv[1], kv[0])
        )
    ]

    vencidas.sort(key=lambda v: (-v.dias_retraso, v.titulo.lower()))

    return EstadisticasTareas(
        mes=mes,
        completadas_mes=completadas_mes,
        por_conviviente=cuotas,
        pendientes=pendientes,
        vencidas=len(vencidas),
        proximas_7_dias=proximas_7,
        completadas_30d=completadas_30d,
        a_tiempo_30d=a_tiempo_30d if con_fecha_30d else None,
        top_vencidas=vencidas[:5],
    )
