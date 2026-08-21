"""Tests de la impresora ESC/POS (Fase 4c) con cliente fake."""

from __future__ import annotations

from datetime import date

import pytest

from backend.models import EntradaListaCompra
from backend.printer import ErrorImpresora, EscposPrinter, build_printer


class FakeClienteEscpos:
    """Fake del ClienteEscpos: registra todo lo que se imprime."""

    def __init__(self, fallar: bool = False) -> None:
        self.textos: list[str] = []
        self.qrs: list[str] = []
        self.cortes = 0
        self.fallar = fallar

    def _quizas_fallar(self) -> None:
        if self.fallar:
            raise ConnectionError("impresora fuera de línea")

    def text(self, texto: str) -> None:
        self._quizas_fallar()
        self.textos.append(texto)

    def qr(self, data: str) -> None:
        self._quizas_fallar()
        self.qrs.append(data)

    def cut(self) -> None:
        self._quizas_fallar()
        self.cortes += 1

    def close(self) -> None:
        pass


def test_print_shopping_list_formato_y_corte() -> None:
    fake = FakeClienteEscpos()
    printer = EscposPrinter(fake)
    items = [
        EntradaListaCompra(
            item_id="item_leche", nombre="Leche entera",
            cantidad=2.0, unidad="litros",
        ),
        EntradaListaCompra(item_id="", nombre="Pan de molde"),
    ]

    lineas = printer.print_shopping_list(items)

    assert lineas == 2
    ticket = "".join(fake.textos)
    assert "LISTA DE LA COMPRA" in ticket
    assert "[ ] Leche entera x2 litros" in ticket
    assert "[ ] Pan de molde" in ticket
    assert fake.cortes == 1


def test_print_shopping_list_error_envuelto() -> None:
    printer = EscposPrinter(FakeClienteEscpos(fallar=True))
    with pytest.raises(ErrorImpresora):
        printer.print_shopping_list([])


def test_print_tupper_label_con_qr() -> None:
    fake = FakeClienteEscpos()
    printer = EscposPrinter(fake)

    printer.print_tupper_label(
        "Pasta con tomate", date(2026, 8, 21), qr_data="homevault://item/tupper_1"
    )

    ticket = "".join(fake.textos)
    assert "Pasta con tomate" in ticket
    assert "Congelado: 2026-08-21" in ticket
    assert fake.qrs == ["homevault://item/tupper_1"]
    assert fake.cortes == 1


def test_print_tupper_label_sin_qr_usa_fecha_de_hoy() -> None:
    fake = FakeClienteEscpos()
    printer = EscposPrinter(fake)

    printer.print_tupper_label("Sopa de verduras")

    ticket = "".join(fake.textos)
    assert f"Congelado: {date.today().isoformat()}" in ticket
    assert fake.qrs == []
    assert fake.cortes == 1


def test_print_tupper_label_error_envuelto() -> None:
    printer = EscposPrinter(FakeClienteEscpos(fallar=True))
    with pytest.raises(ErrorImpresora):
        printer.print_tupper_label("Sopa", date(2026, 8, 21), "qr")


def test_build_printer_sin_host_devuelve_none() -> None:
    assert build_printer(None) is None
