"""Tests de roundtrip parse/serialize de los 4 esquemas sin perder cuerpo."""

from __future__ import annotations

import frontmatter

from backend.models import Consumible, PlanSemanal, Receta, Tarea

CUERPO_CONSUMIBLE = "\n# Ficha\n\nTexto libre con **markdown**.\n"

DOC_CONSUMIBLE = """---
id: "item_milk_01"
nombre: "Leche entera fresca"
ean_barcode: "8410000001234"
categoria: "lacteos"
ubicacion: "nevera"
stock_actual: 2.0
stock_minimo: 3.0
unidad: "litros"
precio_unitario_estimado: 1.15
fecha_caducidad_proxima: "2026-08-28"
fecha_congelacion: null
dias_max_congelador: null
lotes:
  - id_lote: "lot_01"
    cantidad: 1.0
    fecha_caducidad: "2026-08-25"
    fecha_adquisicion: "2026-08-18"
es_reserva_estrategica: false
mqtt_sensor_topic: "home/sensors/kitchen/fridge/milk_weight"
dias_promedio_consumo: 4.5
ultimo_consumo: "2026-08-19T18:30:00Z"
auto_lista_compra: true
tags: [desayuno, basico, fresco]
ultima_actualizacion: "2026-08-20T17:00:00Z"
---
""" + CUERPO_CONSUMIBLE

DOC_RECETA = """---
id: "recipe_pasta_01"
titulo: "Pasta Carbonara Tradicional"
categoria: "comida"
tiempo_minutos: 25
raciones: 2
calorias_racion: 650
ingredientes:
  - item_id: "item_pasta_spaghetti"
    nombre: "Espaguetis"
    cantidad: 200
    unidad: "gramos"
tags: [rapida, italiana, pasta]
---

# Pasos de la receta
"""

DOC_PLANIFICADOR = """---
semana_iso: "2026-W34"
fecha_inicio: "2026-08-17"
fecha_fin: "2026-08-23"
dias:
  lunes:
    comida: { receta_id: "recipe_pasta_01", raciones: 2, stock_deducido: true }
    cena: { receta_id: null, plato_libre: "Tortilla francesa", stock_deducido: false }
batch_cooking_programado:
  - fecha: "2026-08-23"
    recetas_a_preparar: ["recipe_lentejas_01"]
    destino_inventario: "congelador"
---

# Notas de la semana
"""

DOC_TAREA = """---
id: "task_air_filter_01"
titulo: "Limpiar y sustituir filtro del purificador de aire"
zona: "dormitorio"
frecuencia: "cada_3_meses"
estado: "pendiente"
asignado_a: "Daniel"
rotacion_convivientes: ["Daniel", "Pareja"]
indice_rotacion_actual: 0
prioridad: "alta"
consumibles_requeridos:
  - item_id: "item_filtro_hepa_purificador"
    cantidad: 1
    unidad: "unidades"
    verificar_stock_previo: true
google_task_id: null
google_calendar_event_id: null
fecha_programada: "2026-08-25"
ultima_realizacion: "2026-05-25T11:00:00Z"
historial_completados:
  - fecha: "2026-05-25"
    usuario: "Daniel"
bloqueada_por_stock: false
---

- [ ] Paso uno
- [ ] Paso dos
"""


def _roundtrip(doc: str, model_cls):
    """Parsea, re-serializa y re-parsea un documento Markdown."""
    post = frontmatter.loads(doc)
    modelo = model_cls.model_validate(post.metadata)
    cuerpo = post.content
    # Re-serializar desde el modelo y re-parsear
    post2 = frontmatter.Post(cuerpo, **modelo.model_dump(mode="json"))
    doc2 = frontmatter.dumps(post2)
    post3 = frontmatter.loads(doc2)
    modelo2 = model_cls.model_validate(post3.metadata)
    return modelo, modelo2, cuerpo, post3.content


def test_roundtrip_consumible() -> None:
    """El esquema A (consumible) sobrevive al roundtrip con su cuerpo intacto."""
    modelo, modelo2, cuerpo, cuerpo2 = _roundtrip(DOC_CONSUMIBLE, Consumible)
    assert modelo == modelo2
    assert cuerpo == cuerpo2
    assert modelo.lotes[0].fecha_caducidad.isoformat() == "2026-08-25"
    assert modelo.fecha_congelacion is None
    assert modelo.ultimo_consumo is not None


def test_roundtrip_receta() -> None:
    """El esquema B (receta) sobrevive al roundtrip con su cuerpo intacto."""
    modelo, modelo2, cuerpo, cuerpo2 = _roundtrip(DOC_RECETA, Receta)
    assert modelo == modelo2
    assert cuerpo == cuerpo2
    assert modelo.ingredientes[0].cantidad == 200


def test_roundtrip_planificador() -> None:
    """El esquema C (planificador) sobrevive al roundtrip con cuerpo intacto."""
    modelo, modelo2, cuerpo, cuerpo2 = _roundtrip(
        DOC_PLANIFICADOR, PlanSemanal
    )
    assert modelo == modelo2
    assert cuerpo == cuerpo2
    assert modelo.dias["lunes"]["cena"].plato_libre == "Tortilla francesa"
    assert modelo.batch_cooking_programado[0].destino_inventario == "congelador"


def test_roundtrip_tarea() -> None:
    """El esquema D (tarea) sobrevive al roundtrip con su cuerpo intacto."""
    modelo, modelo2, cuerpo, cuerpo2 = _roundtrip(DOC_TAREA, Tarea)
    assert modelo == modelo2
    assert cuerpo == cuerpo2
    assert modelo.consumibles_requeridos[0].verificar_stock_previo is True
    assert modelo.historial_completados[0].usuario == "Daniel"


def test_serializacion_conserva_nulos() -> None:
    """Los campos null del frontmatter se conservan al serializar."""
    post = frontmatter.loads(DOC_CONSUMIBLE)
    modelo = Consumible.model_validate(post.metadata)
    metadata = modelo.model_dump(mode="json")
    assert metadata["fecha_congelacion"] is None
    assert metadata["dias_max_congelador"] is None
