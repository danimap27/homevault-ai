"""Router de escaneo de códigos de barras (Fase 4b).

GET /api/barcode/{ean}: si el EAN ya existe en el vault devuelve el ítem
directamente; si no, consulta Open Food Facts (OFFClient inyectable) y crea
inventario/despensa/item_<slug>.md con el esquema exacto de Consumible
(stock 0, stock_minimo 1, ean_barcode, auto_lista_compra activado) y el
nombre/marca/alérgenos/tabla nutricional en el cuerpo Markdown.

POST /api/barcode/consume: descuenta `cantidad` de unidades resolviendo el
ítem por su EAN, delegando en el motor FIFO de VaultManager.consume_item.
Tras consumir, intenta tachar el ítem de `listas/compra.md` y devuelve el
número de líneas tachadas.

POST /api/barcode/register: registro manual o por fusión de un producto
a partir de su EAN, con soporte para fotos del producto y del precio.

El integrador debe registrar este router en main.py:
    from backend.routers.barcode import router as barcode_router
    app.include_router(barcode_router)
y exponer el cliente OFF y el ReceiptParser en el lifespan:
    app.state.off_client = build_off_client()
    app.state.receipt_parser = build_receipt_parser(vault, settings)
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import uuid
from datetime import date
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.ai_vision_parser import (
    ReceiptParser,
    _slugificar,
    extraer_precio_desde_imagen,
)
from backend.local_barcodes import LocalBarcode, LocalBarcodeManager
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
    """Respuesta de GET /api/barcode/{ean} cuando se encuentra el ítem."""

    item: Consumible
    creado: bool
    origen: Literal["vault", "local", "off"]
    producto_off: Optional[ProductoOFF] = None


class SugerenciaFusion(BaseModel):
    """Ítem existente sugerido para fusionar con un EAN desconocido."""

    id: str
    nombre: str
    ean_barcode: Optional[str] = None


class RespuestaNoEncontrado(BaseModel):
    """Respuesta estructurada de 404 para un EAN no registrado."""

    detail: str
    ean: str
    sugerencias: list[SugerenciaFusion]


class RespuestaConsumoBarcode(BaseModel):
    """Respuesta de POST /api/barcode/consume."""

    resultado: ResultadoConsumo
    quitado_de_lista: int


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


def _receipt_parser(request: Request) -> Optional[ReceiptParser]:
    """Recupera el ReceiptParser del estado de la app, si existe."""
    return getattr(request.app.state, "receipt_parser", None)


def _local_barcode_manager(request: Request) -> LocalBarcodeManager:
    """Recupera o crea el LocalBarcodeManager ligado al vault actual."""
    return LocalBarcodeManager(request.app.state.vault.vault_path)


def _extension_segura(content_type: Optional[str]) -> str:
    """Devuelve una extensión de imagen segura a partir del content-type."""
    if content_type:
        extension = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if extension:
            return extension.lstrip(".")
    return "jpg"


def _ruta_assets_productos(vault: VaultManager) -> Path:
    """Devuelve el directorio de fotos de productos, creándolo si falta."""
    ruta = vault.vault_path / "assets" / "productos"
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


async def _guardar_foto_producto(
    vault: VaultManager,
    item_id: str,
    archivo: UploadFile,
) -> str:
    """Persiste la foto de un producto y devuelve la ruta relativa al vault."""
    datos = await archivo.read()
    extension = _extension_segura(archivo.content_type)
    ruta = _ruta_assets_productos(vault) / f"{item_id}.{extension}"
    await asyncio.to_thread(ruta.write_bytes, datos)
    return f"assets/productos/{item_id}.{extension}"


async def _actualizar_item(
    vault: VaultManager,
    item_id: str,
    modificador,
) -> Consumible:
    """Lee un ítem, aplica una función modificadora y lo vuelve a escribir.

    La función modificador recibe (item, cuerpo) y debe devolver
    (item, cuerpo) actualizados.
    """
    path = await vault._find_item_path(item_id)
    if path is None:
        raise KeyError(f"Ítem no encontrado: {item_id}")
    lock = await vault._get_lock(path)
    async with lock:
        item, cuerpo = await vault._read_doc(path, Consumible)
        item, cuerpo = await modificador(item, cuerpo)
        await vault._write_doc(path, item, cuerpo)
    return item


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


async def _crear_item_desde_local_barcode(
    vault: VaultManager, barcode: LocalBarcode
) -> Consumible:
    """Crea un Consumible a partir de un código de barras local.

    El ítem nace con stock_actual 0, stock_minimo 1, ean_barcode y
    auto_lista_compra activado; la información local va en el cuerpo Markdown.
    """
    slug = _slugificar(barcode.nombre)
    item_id = f"item_{slug}"
    if await vault.get_item(item_id) is not None:
        item_id = f"item_{slug}_{uuid.uuid4().hex[:6]}"
    nuevo = Consumible(
        id=item_id,
        nombre=barcode.nombre,
        ean_barcode=barcode.ean,
        categoria=barcode.categoria,
        ubicacion=barcode.ubicacion,
        stock_actual=0.0,
        stock_minimo=1.0,
        unidad=barcode.unidad,
        precio_unitario_estimado=barcode.precio_unitario_estimado,
        lotes=[],
        auto_lista_compra=True,
        tags=barcode.tags + ["local_barcode"],
        ultima_actualizacion=ahora_utc(),
    )
    ruta = vault.vault_path / "inventario" / barcode.ubicacion / f"{item_id}.md"
    cuerpo = (
        f"# {barcode.nombre}\n\n"
        f"**Código de barras:** {barcode.ean}\n\n"
        f"Producto registrado desde la base de datos local de códigos de barras.\n"
    )
    await vault._write_doc(ruta, nuevo, cuerpo)
    logger.info("Ítem creado desde local barcode: %s (%s)", item_id, ruta)
    return nuevo


async def _sugerencias_fusion(
    vault: VaultManager, limite: int = 10
) -> list[SugerenciaFusion]:
    """Devuelve los primeros N ítems del vault ordenados por nombre."""
    items = await vault.list_items()
    items.sort(key=lambda i: i.nombre.casefold())
    return [
        SugerenciaFusion(
            id=item.id, nombre=item.nombre, ean_barcode=item.ean_barcode
        )
        for item in items[:limite]
    ]


async def _resolver_precio_desde_foto(
    parser: Optional[ReceiptParser],
    foto_precio: Optional[UploadFile],
    precio_param: Optional[float],
) -> Optional[float]:
    """Devuelve el precio final priorizando la extracción por IA sobre el parámetro.

    Si hay foto de precio y un parser configurado, intenta extraer el importe.
    Cuando el importe detectado es mayor que 0, sobrescribe el precio recibido.
    """
    if foto_precio is None or parser is None:
        return precio_param
    datos = await foto_precio.read()
    mime_type = foto_precio.content_type or "image/jpeg"
    try:
        extraido = await extraer_precio_desde_imagen(parser, datos, mime_type)
    except Exception as exc:
        logger.warning("No se pudo extraer el precio de la imagen: %s", exc)
        return precio_param
    if extraido is not None and extraido > 0:
        return extraido
    return precio_param


@router.get("/{ean}", response_model=RespuestaBarcode)
async def escanear_barcode(
    request: Request, ean: str
) -> RespuestaBarcode | JSONResponse:
    """Resuelve un código de barras: vault, local barcodes, Open Food Facts.

    Si el EAN no existe en ninguna fuente, devuelve 404 con una lista de
    sugerencias de ítems existentes para posible fusión.
    """
    vault = _vault(request)
    existente = await vault.get_item_by_ean(ean)
    if existente is not None:
        return RespuestaBarcode(item=existente, creado=False, origen="vault")

    local_manager = _local_barcode_manager(request)
    local = local_manager.obtener(ean)
    if local is not None:
        item = await _crear_item_desde_local_barcode(vault, local)
        return RespuestaBarcode(item=item, creado=True, origen="local")

    cliente = _off_client(request)
    try:
        datos = await cliente.get_product(ean)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error consultando Open Food Facts: {exc}",
        ) from exc
    if datos is None:
        return JSONResponse(
            status_code=404,
            content=RespuestaNoEncontrado(
                detail="Producto no encontrado",
                ean=ean,
                sugerencias=await _sugerencias_fusion(vault),
            ).model_dump(),
        )
    producto = map_off_to_consumible(datos, ean)
    item = await _crear_item_desde_off(vault, producto)
    return RespuestaBarcode(
        item=item, creado=True, origen="off", producto_off=producto
    )


@router.post("/consume", response_model=RespuestaConsumoBarcode)
async def consumir_por_barcode(
    request: Request, peticion: PeticionConsumoBarcode
) -> RespuestaConsumoBarcode:
    """Consume unidades de un ítem resolviéndolo por su código de barras.

    Tras consumir, intenta tachar el ítem de la lista de la compra.
    """
    vault = _vault(request)
    item = await vault.get_item_by_ean(peticion.ean)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ítem no encontrado para el EAN: {peticion.ean}",
        )
    resultado = await vault.consume_item(item.id, peticion.cantidad)
    quitado_de_lista = await vault.check_shopping_list_entry(item.id)
    return RespuestaConsumoBarcode(
        resultado=resultado, quitado_de_lista=quitado_de_lista
    )


@router.post("/register", response_model=Consumible)
async def registrar_producto_barcode(
    request: Request,
    ean: str = Form(...),
    nombre: str = Form(...),
    categoria: str = Form(default="despensa_seca"),
    ubicacion: str = Form(default="despensa"),
    unidad: str = Form(default="unidades"),
    precio: Optional[float] = Form(default=None),
    cantidad: float = Form(default=1.0),
    fecha_caducidad: Optional[date] = Form(default=None),
    supermercado: Optional[str] = Form(default=None),
    foto_producto: Optional[UploadFile] = File(default=None),
    foto_precio: Optional[UploadFile] = File(default=None),
    merge_target_id: Optional[str] = Form(default=None),
) -> Consumible:
    """Registra manualmente un producto a partir de su EAN o lo fusiona con uno existente.

    Si se proporciona `merge_target_id`, el EAN se añade al ítem existente y se
    registra una compra. En caso contrario se crea un nuevo Consumible con el
    EAN y, opcionalmente, un primer lote.

    Las fotos del producto se guardan en `vault/assets/productos/`. Si se envía
    `foto_precio` y hay un proveedor de IA configurado, se intenta extraer el
    importe y sobrescribir el precio indicado.
    """
    vault = _vault(request)

    # Validación de catálogos
    from backend.ai_vision_parser import (
        UBICACIONES_VALIDAS,
        UNIDADES_VALIDAS,
    )

    categoria_manager = _vault(request).categoria_manager
    if not categoria_manager.existe(categoria):
        raise HTTPException(
            status_code=400,
            detail=f"Categoría no válida: {categoria}",
        )
    if ubicacion not in UBICACIONES_VALIDAS:
        raise HTTPException(
            status_code=400,
            detail=f"Ubicación no válida: {ubicacion}",
        )
    if unidad not in UNIDADES_VALIDAS:
        raise HTTPException(
            status_code=400,
            detail=f"Unidad no válida: {unidad}",
        )

    parser = _receipt_parser(request)
    precio_final = await _resolver_precio_desde_foto(parser, foto_precio, precio)

    if merge_target_id is not None:
        existente = await vault.get_item(merge_target_id)
        if existente is None:
            raise HTTPException(
                status_code=404,
                detail=f"Ítem destino de fusión no encontrado: {merge_target_id}",
            )

        async def _fusionar(item: Consumible, cuerpo: str) -> tuple[Consumible, str]:
            item.ean_barcode = ean
            item.ultima_actualizacion = ahora_utc()
            if foto_producto is not None:
                ruta_relativa = await _guardar_foto_producto(
                    vault, item.id, foto_producto
                )
                cuerpo = (
                    f"{cuerpo.rstrip()}\n\n![Foto del producto]({ruta_relativa})\n"
                )
            return item, cuerpo

        await _actualizar_item(vault, merge_target_id, _fusionar)

        if cantidad > 0 and precio_final is not None and precio_final >= 0:
            await vault.add_purchase(
                merge_target_id,
                cantidad,
                precio_final,
                fecha_caducidad,
                supermercado=supermercado,
            )

        return await vault.get_item(merge_target_id)

    # Creación de un ítem nuevo
    slug = _slugificar(nombre)
    item_id = f"item_{slug}_{uuid.uuid4().hex[:8]}"
    while await vault.get_item(item_id) is not None:
        item_id = f"item_{slug}_{uuid.uuid4().hex[:8]}"

    cuerpo_lineas = [f"# {nombre}", ""]
    ruta_foto: Optional[str] = None
    if foto_producto is not None:
        ruta_foto = await _guardar_foto_producto(vault, item_id, foto_producto)
        cuerpo_lineas.append(f"![Foto del producto]({ruta_foto})")
        cuerpo_lineas.append("")
    cuerpo_lineas.append("Registro manual desde escaneo de código de barras.\n")

    nuevo = Consumible(
        id=item_id,
        nombre=nombre,
        ean_barcode=ean,
        categoria=categoria,
        ubicacion=ubicacion,
        stock_actual=0.0,
        stock_minimo=1.0,
        unidad=unidad,
        lotes=[],
        auto_lista_compra=True,
        ultima_actualizacion=ahora_utc(),
    )
    ruta = vault.vault_path / "inventario" / ubicacion / f"{item_id}.md"
    await vault._write_doc(ruta, nuevo, "\n".join(cuerpo_lineas))

    if cantidad > 0 and precio_final is not None and precio_final >= 0:
        await vault.add_purchase(
            item_id, cantidad, precio_final, fecha_caducidad,
            supermercado=supermercado,
        )

    logger.info("Ítem registrado manualmente: %s (%s)", item_id, ruta)
    return await vault.get_item(item_id)
