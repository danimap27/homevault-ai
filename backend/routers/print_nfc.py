"""Router de impresión ESC/POS y ubicaciones NFC (Fase 4c).

Endpoints:
- POST /api/print/receipt-list   -> imprime las entradas pendientes de la lista
- POST /api/print/label-tupper   -> imprime etiqueta de tupper (nombre+fecha+QR)
- GET  /location/{slug}          -> ítems de una ubicación (para tags NFC)

La impresora se resuelve desde app.state.printer (inyectable en tests); si no
está cableada, se construye perezosamente desde las variables de entorno
PRINTER_HOST / PRINTER_PORT. Sin impresora configurada responde 503.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.models import Consumible
from backend.printer import ErrorImpresora, EscposPrinter, build_printer
from backend.vault_manager import VaultManager

router = APIRouter(tags=["print-nfc"])


class PeticionEtiquetaTupper(BaseModel):
    """Cuerpo de POST /api/print/label-tupper."""

    nombre: str
    fecha_congelacion: Optional[date] = None  # por defecto: hoy
    qr_data: str = ""


class RespuestaImpresion(BaseModel):
    """Resultado de una operación de impresión."""

    impreso: bool
    lineas: int = 0


class RespuestaUbicacion(BaseModel):
    """Contenido de una ubicación física (tag NFC)."""

    slug: str
    nombre: str
    tipo: str
    items: list[Consumible]


def _vault(request: Request) -> VaultManager:
    """Recupera el VaultManager del estado de la app."""
    return request.app.state.vault


def _printer(request: Request) -> EscposPrinter:
    """Recupera (o construye perezosamente) la impresora de la app."""
    printer: Optional[EscposPrinter] = getattr(
        request.app.state, "printer", None
    )
    if printer is None:
        host = os.getenv("PRINTER_HOST")
        port = int(os.getenv("PRINTER_PORT", "9100"))
        printer = build_printer(host, port)
        request.app.state.printer = printer
    if printer is None:
        raise HTTPException(
            status_code=503,
            detail="Impresora no configurada (PRINTER_HOST)",
        )
    return printer


@router.post("/api/print/receipt-list", response_model=RespuestaImpresion)
async def imprimir_lista_compra(request: Request) -> RespuestaImpresion:
    """Imprime en la térmica las entradas pendientes de listas/compra.md."""
    printer = _printer(request)
    pendientes = [
        entrada
        for entrada in await _vault(request).get_shopping_list()
        if not entrada.comprado
    ]
    try:
        lineas = printer.print_shopping_list(pendientes)
    except ErrorImpresora as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RespuestaImpresion(impreso=True, lineas=lineas)


@router.post("/api/print/label-tupper", response_model=RespuestaImpresion)
async def imprimir_etiqueta_tupper(
    request: Request, peticion: PeticionEtiquetaTupper
) -> RespuestaImpresion:
    """Imprime la etiqueta de un tupper (nombre, fecha de congelación y QR)."""
    printer = _printer(request)
    try:
        printer.print_tupper_label(
            peticion.nombre, peticion.fecha_congelacion, peticion.qr_data
        )
    except ErrorImpresora as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RespuestaImpresion(impreso=True, lineas=1)


@router.get("/location/{slug}", response_model=RespuestaUbicacion)
async def items_por_ubicacion(request: Request, slug: str) -> RespuestaUbicacion:
    """Ítems de una ubicación física, leída de config/ubicaciones.json.

    Pensado para tags NFC: escanear el tag de una estantería abre el listado
    de lo que hay en ella.
    """
    vault = _vault(request)
    ruta = vault.vault_path / "config" / "ubicaciones.json"
    if not ruta.exists():
        raise HTTPException(
            status_code=404,
            detail="No existe config/ubicaciones.json en el vault",
        )
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500, detail=f"ubicaciones.json inválido: {exc}"
        ) from exc
    ubicaciones = {u["id"]: u for u in datos.get("ubicaciones", [])}
    ubicacion = ubicaciones.get(slug)
    if ubicacion is None:
        raise HTTPException(
            status_code=404, detail=f"Ubicación no encontrada: {slug}"
        )
    items = await vault.list_items(ubicacion=slug)
    return RespuestaUbicacion(
        slug=slug,
        nombre=ubicacion.get("nombre", slug),
        tipo=ubicacion.get("tipo", ""),
        items=items,
    )
