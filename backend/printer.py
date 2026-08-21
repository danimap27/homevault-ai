"""Impresión térmica ESC/POS (Fase 4c).

La lógica de formato vive en EscposPrinter, que trabaja contra un cliente
ESC/POS INYECTADO con la interfaz mínima `text`/`qr`/`cut`/`close`, lo que
permite testear con fakes sin hardware. La construcción de la impresora de
red real (python-escpos) está encapsulada en build_printer() con import
perezoso para no obligar a tener la dependencia importable en tests.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional, Protocol

from backend.models import EntradaListaCompra
from backend.vault_manager import ahora_utc

logger = logging.getLogger(__name__)

ANCHO_TICKET = 32  # caracteres por línea en una térmica de 58 mm


class ErrorImpresora(Exception):
    """Fallo de comunicación o de formato con la impresora ESC/POS."""


class ClienteEscpos(Protocol):
    """Interfaz mínima del cliente ESC/POS (fácil de falsear)."""

    def text(self, texto: str) -> None:
        """Imprime texto plano."""
        ...

    def qr(self, data: str) -> None:
        """Imprime un código QR con el contenido dado."""
        ...

    def cut(self) -> None:
        """Corta el papel."""
        ...

    def close(self) -> None:
        """Cierra la conexión con la impresora."""
        ...


def _separador() -> str:
    """Línea separadora del ancho del ticket."""
    return "-" * ANCHO_TICKET + "\n"


class EscposPrinter:
    """Impresora térmica con formato de tickets de HomeVault AI."""

    def __init__(self, cliente: ClienteEscpos) -> None:
        self._cliente = cliente

    def print_shopping_list(self, items: list[EntradaListaCompra]) -> int:
        """Imprime la lista de la compra; devuelve el nº de líneas impresas.

        Solo tiene sentido pasar entradas pendientes; el router ya las filtra.
        """
        try:
            self._cliente.text("LISTA DE LA COMPRA\n")
            self._cliente.text(_separador())
            for item in items:
                cantidad = (
                    f" x{item.cantidad:g} {item.unidad}"
                    if item.cantidad is not None
                    else ""
                )
                self._cliente.text(f"[ ] {item.nombre}{cantidad}\n")
            self._cliente.text(_separador())
            self._cliente.text(
                f"Generada: {ahora_utc():%Y-%m-%d %H:%M} UTC\n"
            )
            self._cliente.cut()
        except Exception as exc:
            raise ErrorImpresora(
                f"No se pudo imprimir la lista de la compra: {exc}"
            ) from exc
        logger.info("Lista de la compra impresa (%d líneas)", len(items))
        return len(items)

    def print_tupper_label(
        self,
        nombre: str,
        fecha_congelacion: Optional[date] = None,
        qr_data: str = "",
    ) -> None:
        """Imprime la etiqueta de un tupper: nombre, fecha y QR opcional."""
        fecha = fecha_congelacion or ahora_utc().date()
        try:
            self._cliente.text(f"{nombre}\n")
            self._cliente.text(f"Congelado: {fecha.isoformat()}\n")
            if qr_data:
                self._cliente.qr(qr_data)
            self._cliente.cut()
        except Exception as exc:
            raise ErrorImpresora(
                f"No se pudo imprimir la etiqueta del tupper: {exc}"
            ) from exc
        logger.info("Etiqueta de tupper impresa: %s", nombre)


def build_printer(host: Optional[str], port: int = 9100) -> Optional[EscposPrinter]:
    """Construye la impresora de red real; None si no hay host configurado.

    El import de python-escpos es perezoso: solo se intenta cuando hay una
    impresora configurada.
    """
    if not host:
        return None
    try:
        from escpos.printer import Network  # import perezoso

        return EscposPrinter(Network(host, port))
    except Exception as exc:
        logger.error("No se pudo inicializar la impresora %s:%s: %s", host, port, exc)
        return None
