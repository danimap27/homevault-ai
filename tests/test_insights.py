"""Tests del motor de inteligencia (backend/insights.py).

Cubre: tasa de consumo y predicciones de agotamiento, sugerencias de
reposición, valor de inventario y estadísticas de tareas con equidad.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from backend.insights import (
    construir_predicciones,
    disponible_total,
    estadisticas_tareas,
    items_bajo_minimo,
    predecir_agotamiento,
    sugerencias_reposicion,
    tasa_consumo_diaria,
    valor_inventario,
)
from backend.models import (
    Consumible,
    ConsumoRegistrado,
    EntradaListaCompra,
    HistorialCompletado,
    Tarea,
)

AHORA = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def _item(**overrides) -> Consumible:
    base: dict = dict(
        id="item_test",
        nombre="Leche entera",
        categoria="lacteos",
        ubicacion="nevera",
        stock_actual=4.0,
        stock_minimo=2.0,
        unidad="litros",
        precio_unitario_estimado=1.0,
    )
    base.update(overrides)
    return Consumible(**base)


def _historial(dias_atras: tuple[int, ...], cantidad: float = 1.0) -> list:
    return [
        ConsumoRegistrado(fecha=AHORA - timedelta(days=d), cantidad=cantidad)
        for d in dias_atras
    ]


# --- Tasa de consumo y predicciones ------------------------------------------


def test_tasa_sin_historial_es_none() -> None:
    assert tasa_consumo_diaria(_item(), ahora=AHORA) is None


def test_tasa_con_historial_suficiente() -> None:
    item = _item(historial_consumo=_historial((30, 25, 20, 15, 10, 5)))
    tasa = tasa_consumo_diaria(item, ahora=AHORA)
    assert tasa == pytest.approx(6.0 / 30.0)


def test_tasa_minimo_dias_observacion() -> None:
    """Con 2 consumos muy recientes, se usa el mínimo de 7 días."""
    item = _item(historial_consumo=_historial((2, 0)))
    tasa = tasa_consumo_diaria(item, ahora=AHORA)
    assert tasa == pytest.approx(2.0 / 7.0)


def test_tasa_ignora_consumos_fuera_de_ventana() -> None:
    item = _item(historial_consumo=_historial((200, 30, 25)))
    tasa = tasa_consumo_diaria(item, ahora=AHORA)
    # Solo entran los dos últimos (hace 30 y 25 días): 2 unidades / 30 días
    assert tasa == pytest.approx(2.0 / 30.0)


def test_prediccion_dias_restantes_y_fecha() -> None:
    item = _item(historial_consumo=_historial((30, 25, 20, 15, 10, 5)))
    prediccion = predecir_agotamiento(item, ahora=AHORA)
    assert prediccion is not None
    # stock 4 / tasa 0.2 por día = 20 días
    assert prediccion.dias_restantes == pytest.approx(20.0)
    assert prediccion.fecha_estimada_agotamiento == date(2026, 10, 16)
    assert prediccion.confianza == "alta"


def test_prediccion_confianza_baja_con_dos_consumos() -> None:
    item = _item(historial_consumo=_historial((10, 5)))
    prediccion = predecir_agotamiento(item, ahora=AHORA)
    assert prediccion is not None
    assert prediccion.confianza == "baja"


def test_prediccion_none_sin_stock_o_sin_historial() -> None:
    assert predecir_agotamiento(_item(), ahora=AHORA) is None
    agotado = _item(stock_actual=0.0, historial_consumo=_historial((10, 5)))
    assert predecir_agotamiento(agotado, ahora=AHORA) is None


def test_construir_predicciones_ordenadas_y_limitadas() -> None:
    urgente = _item(id="a", nombre="Agua", historial_consumo=_historial((5, 0)), stock_actual=1.0)
    tranquilo = _item(
        id="b",
        nombre="Arroz",
        historial_consumo=_historial((40, 35, 25, 15, 5)),
        stock_actual=20.0,
        unidad="kg",
    )
    sin_datos = _item(id="c", nombre="Sal")
    predicciones = construir_predicciones([tranquilo, urgente, sin_datos], ahora=AHORA)
    assert [p.item_id for p in predicciones] == ["a", "b"]
    limitadas = construir_predicciones([urgente, tranquilo], ahora=AHORA, limite=1)
    assert [p.item_id for p in limitadas] == ["a"]


# --- Reposición y valor --------------------------------------------------------


def test_sugerencias_incluye_agotado_y_bajo_minimo() -> None:
    agotado = _item(
        id="a",
        nombre="Agua",
        stock_actual=0.0,
        historial_consumo=_historial((20, 10)),
    )
    bajo = _item(
        id="b",
        nombre="Pan",
        stock_actual=1.0,
        stock_minimo=2.0,
        historial_consumo=_historial((12, 3)),
    )
    sano = _item(id="c", nombre="Sal", stock_actual=10.0, stock_minimo=1.0)
    sugerencias = sugerencias_reposicion([agotado, bajo, sano], ahora=AHORA)
    assert [s.item_id for s in sugerencias] == ["a", "b"]
    assert sugerencias[0].urgencia == "critica"
    assert sugerencias[1].urgencia == "alta"
    assert "Sin stock" in sugerencias[0].motivo
    assert "mínimo" in sugerencias[1].motivo


def test_sugerencias_ignora_placeholder_nunca_usado() -> None:
    """Sin lotes, sin historial y sin consumo no hay nada que reponer."""
    placeholder = _item(
        id="p",
        nombre="Focaccia",
        stock_actual=0.0,
        stock_minimo=1.0,
        precio_unitario_estimado=2.0,
    )
    assert sugerencias_reposicion([placeholder], ahora=AHORA) == []
    # En cambio, si se compró alguna vez (tiene lotes), sí se sugiere
    comprado = _item(
        id="q",
        nombre="Focaccia",
        stock_actual=0.0,
        stock_minimo=1.0,
        lotes=[],
        historial_consumo=_historial((15, 5)),
    )
    assert [s.item_id for s in sugerencias_reposicion([comprado], ahora=AHORA)] == ["q"]


def test_sugerencias_prediccion_dentro_del_horizonte() -> None:
    # Tasa 0.2/día con stock 2 => agota en 10 días (< 14): entra por predicción
    item = _item(
        stock_actual=2.0,
        stock_minimo=0.0,
        historial_consumo=_historial((30, 25, 20, 15, 10, 5)),
    )
    sugerencias = sugerencias_reposicion([item], ahora=AHORA)
    assert len(sugerencias) == 1
    assert sugerencias[0].dias_restantes == pytest.approx(10.0)
    assert "Se agota" in sugerencias[0].motivo


def test_sugerencias_marca_ya_en_lista() -> None:
    agotado = _item(
        id="a",
        nombre="Agua",
        stock_actual=0.0,
        historial_consumo=_historial((18, 6)),
    )
    entradas = [
        EntradaListaCompra(item_id="a", nombre="Agua", comprado=False),
    ]
    sugerencias = sugerencias_reposicion([agotado], entradas, ahora=AHORA)
    assert sugerencias[0].ya_en_lista is True

    comprado = [
        EntradaListaCompra(item_id="a", nombre="Agua", comprado=True),
    ]
    sugerencias = sugerencias_reposicion([agotado], comprado, ahora=AHORA)
    assert sugerencias[0].ya_en_lista is False


def test_sugerencias_match_por_nombre() -> None:
    agotado = _item(
        id="x",
        nombre="  Leche   Entera ",
        stock_actual=0.0,
        historial_consumo=_historial((20, 5)),
    )
    entradas = [EntradaListaCompra(item_id="otro", nombre="leche entera", comprado=False)]
    sugerencias = sugerencias_reposicion([agotado], entradas, ahora=AHORA)
    assert sugerencias[0].ya_en_lista is True


def test_valor_inventario_y_bajo_minimo() -> None:
    a = _item(id="a", stock_actual=4.0, precio_unitario_estimado=1.5)
    b = _item(id="b", stock_actual=2.0, stock_minimo=0.0, precio_unitario_estimado=None)
    c = _item(id="c", stock_actual=0.5, stock_minimo=1.0, precio_unitario_estimado=2.0)
    assert valor_inventario([a, b, c]) == pytest.approx(7.0)
    assert items_bajo_minimo([a, b, c]) == 1
    assert disponible_total(a) == 4.0


# --- Estadísticas de tareas ----------------------------------------------------


def _tarea(**overrides) -> Tarea:
    base: dict = dict(
        id="t1",
        titulo="Limpiar el baño",
        asignado_a="Daniel",
        fecha_programada=date(2026, 9, 20),
    )
    base.update(overrides)
    return Tarea(**base)


def test_estadisticas_completadas_y_equidad() -> None:
    tareas = [
        _tarea(
            id="t1",
            historial_completados=[
                HistorialCompletado(fecha=date(2026, 9, 10), usuario="Daniel"),
                HistorialCompletado(fecha=date(2026, 9, 21), usuario="Pareja"),
                HistorialCompletado(fecha=date(2026, 8, 30), usuario="Daniel"),
            ],
        ),
        _tarea(id="t2", historial_completados=[]),
    ]
    stats = estadisticas_tareas(tareas, ahora=AHORA)
    assert stats.mes == "2026-09"
    assert stats.completadas_mes == 2
    assert {c.nombre: c.completadas for c in stats.por_conviviente} == {
        "Daniel": 1,
        "Pareja": 1,
    }
    assert all(c.porcentaje == pytest.approx(50.0) for c in stats.por_conviviente)


def test_estadisticas_vencidas_y_proximas() -> None:
    tareas = [
        _tarea(id="vencida", fecha_programada=date(2026, 9, 20), prioridad="alta"),
        _tarea(id="proxima", fecha_programada=date(2026, 9, 30)),
        _tarea(id="lejana", fecha_programada=date(2026, 10, 30)),
        _tarea(id="sin_fecha", fecha_programada=None),
        _tarea(
            id="completada",
            estado="completada",
            fecha_programada=date(2026, 9, 1),
        ),
    ]
    stats = estadisticas_tareas(tareas, ahora=AHORA)
    assert stats.pendientes == 4
    assert stats.vencidas == 1
    assert stats.proximas_7_dias == 1
    assert stats.top_vencidas[0].task_id == "vencida"
    assert stats.top_vencidas[0].dias_retraso == 6


def test_estadisticas_puntualidad_30d() -> None:
    tareas = [
        _tarea(
            id="a",
            fecha_programada=date(2026, 9, 21),
            historial_completados=[
                HistorialCompletado(fecha=date(2026, 9, 20), usuario="Daniel")
            ],
        ),
        _tarea(
            id="b",
            fecha_programada=date(2026, 9, 5),
            historial_completados=[
                HistorialCompletado(fecha=date(2026, 9, 10), usuario="Daniel")
            ],
        ),
        _tarea(
            id="c",
            fecha_programada=None,
            historial_completados=[
                HistorialCompletado(fecha=date(2026, 9, 15), usuario="Pareja")
            ],
        ),
    ]
    stats = estadisticas_tareas(tareas, ahora=AHORA)
    assert stats.completadas_30d == 3
    assert stats.a_tiempo_30d == 1  # solo la primera cumple fecha <= programada


def test_estadisticas_usuario_anonimo() -> None:
    tareas = [
        _tarea(
            id="t1",
            historial_completados=[
                HistorialCompletado(fecha=date(2026, 9, 10), usuario=None)
            ],
        )
    ]
    stats = estadisticas_tareas(tareas, ahora=AHORA)
    assert stats.por_conviviente[0].nombre == "Sin asignar"
