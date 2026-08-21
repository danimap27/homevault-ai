"""Router de escaneo de códigos de barras (Fase 4b).

GET /api/barcode/{ean}: si el EAN ya existe en el vault devuelve el ítem
directamente; si no, consulta Open Food Facts (OFFClient inyectable) y crea
inventario/despensa/item_<slug>.md con el esquema exacto de Consumible
(stock 0, stock_minimo 1, ean_barcode, auto_lista_compra activado) y el
nombre/marca/alérgenos/tabla nutricional en el cuerpo Markdown.

POST /api/barcode/consume: descuenta `cantidad` de unidades resolviendo el
ítem por su EAN, delegando en el motor FIFO de VaultManager.consume_item.

El integrador debe registrar este router en main.py:
    from backend.routers.barcode import router as barcode_router
    app.include_router(barcode_router)
y exponer el cliente OFF en el lifespan:
    app.state.off_client = build_off_client()
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.ai_vision_parser import _slugificar
from backend.models import Consumible, ResultadoConsumo
from backend.off_client import OFFClient, ProductoOFF, map_off_to_consumible
from backend.vault_manager import VaultManager, ahora_utc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/barcode", tags=["barcode"])


class PeticionConsumoBarcode(BaseModel):
    """Cuerpo de POST /api/barcode/consume."""

    ean: str
    cantidad: float = Field(default=1.0, gt=0)


class RespuestaBarcode(BaseModel):
    """Respuesta de GET /api/barcode/{ean}."""

    item: Consumible
    creado: bool
    origen: Literal["vault", "off"]
    producto_off: Optional[ProductoOFF] = None


def _vault(request: Request) -> VaultManager:
    """Recupera el VaultManager del estado de la app."""
    return request.app.state.vault


def _off_client(request: Request) -> OFFClient:
    """Recupera el OFFClient del estado de la app (503 si no configurado)."""
    cliente: Optional[OFFClient] = getattr(request.app.state, "off_client", None)
    if cliente is None:
        raise HTTPException(
            status_code=503,
            detail="Cliente de Open Food Facts no configurado (OFF_*)",
        )
    return cliente


def _cuerpo_item_off(producto: ProductoOFF) -> str:
    """Cuerpo Markdown del ítem creado desde OFF (ficha del producto)."""
    lineas = [f"# {producto.nombre}", ""]
    if producto.marcas:
        lineas.append(f"**Marca:** {', '.join(producto.marcas)}")
        lineas.append("")
    lineas.append(f"**Código de barras:** {producto.ean}")
    lineas.append("")
    if producto.alergenos:
        lineas.append("## Alérgenos")
        lineas.append("")
        lineas.extend(f"- {alergeno}" for alergeno in producto.alergenos)
        lineas.append("")
    if producto.kcal_100g is not None or producto.proteinas_100g is not None:
        lineas.append("## Información nutricional (por 100 g)")
        lineas.append("")
        lineas.append("| Nutriente | Valor |")
        lineas.append("| --- | --- |")
        if producto.kcal_100g is not None:
            lineas.append(f"| Energía | {producto.kcal_100g:g} kcal |")
        if producto.proteinas_100g is not None:
            lineas.append(f"| Proteínas | {producto.proteinas_100g:g} g |")
        lineas.append("")
    if producto.imagen_url:
        lineas.append(f"![Imagen del producto]({producto.imagen_url})")
        lineas.append("")
    lineas.append(
        "Fuente: [Open Food Facts]"
        f"(https://world.openfoodfacts.org/product/{producto.ean})"
    )
    return "\n".join(lineas) + "\n"


async def _crear_item_desde_off(
    vault: VaultManager, producto: ProductoOFF
) -> Consumible:
    """Crea inventario/despensa/item_<slug>.md con el esquema de Consumible.

    El ítem nace con stock_actual 0, stock_minimo 1, ean_barcode y
    auto_lista_compra activado; la ficha OFF va en el cuerpo Markdown.
    """
    slug = _slugificar(producto.nombre)
    item_id = f"item_{slug}"
    if await vault.get_item(item_id) is not None:
        item_id = f"item_{slug}_{uuid.uuid4().hex[:6]}"
    nuevo = Consumible(
        id=item_id,
        nombre=producto.nombre,
        ean_barcode=producto.ean,
        categoria="despensa_seca",
        ubicacion="despensa",
        stock_actual=0.0,
        stock_minimo=1.0,
        unidad="unidades",
        lotes=[],
        auto_lista_compra=True,
        tags=["openfoodfacts"],
        ultima_actualizacion=ahora_utc(),
    )
    ruta = vault.vault_path / "inventario" / "despensa" / f"{item_id}.md"
    await vault._write_doc(ruta, nuevo, _cuerpo_item_off(producto))
    logger.info("Ítem creado desde OFF: %s (%s)", item_id, ruta)
    return nuevo


@router.get("/{ean}", response_model=RespuestaBarcode)
async def escanear_barcode(request: Request, ean: str) -> RespuestaBarcode:
    """Resuelve un código de barras: vault primero, Open Food Facts después."""
    vault = _vault(request)
    existente = await vault.get_item_by_ean(ean)
    if existente is not None:
        return RespuestaBarcode(item=existente, creado=False, origen="vault")

    cliente = _off_client(request)
    try:
        datos = await cliente.get_product(ean)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error consultando Open Food Facts: {exc}",
        ) from exc
    if datos is None:
        raise HTTPException(
            status_code=404,
            detail=f"Producto no encontrado en Open Food Facts: {ean}",
        )
    producto = map_off_to_consumible(datos, ean)
    item = await _crear_item_desde_off(vault, producto)
    return RespuestaBarcode(
        item=item, creado=True, origen="off", producto_off=producto
    )


@router.post("/consume", response_model=ResultadoConsumo)
async def consumir_por_barcode(
    request: Request, peticion: PeticionConsumoBarcode
) -> ResultadoConsumo:
    """Consume unidades de un ítem resolviéndolo por su código de barras."""
    vault = _vault(request)
    item = await vault.get_item_by_ean(peticion.ean)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ítem no encontrado para el EAN: {peticion.ean}",
        )
    return await vault.consume_item(item.id, peticion.cantidad)
