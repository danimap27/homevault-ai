"""Base de datos local de códigos de barras de HomeVault AI.

Persiste en ``vault/config/barcodes.json`` y actúa como segunda fuente de
resolución de EANs (después del vault y antes de Open Food Facts). Permite
gestionar productos habituales españoles sin depender de conexión externa.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from backend.categorias import CategoriaManager
from backend.models import Ubicacion, Unidad


class LocalBarcode(BaseModel):
    """Producto conocido localmente por su EAN."""

    ean: str
    nombre: str
    categoria: str
    ubicacion: Ubicacion
    unidad: Unidad
    supermercado: Optional[str] = None
    precio_unitario_estimado: Optional[float] = None
    tags: list[str] = Field(default_factory=list)


# Población inicial de productos españoles comunes. Los EANs son ficticios
# pero realistas: 13 dígitos que empiezan por 84.
_BARCODES_INICIALES: list[LocalBarcode] = [
    LocalBarcode(ean="8400000000100", nombre="Leche entera 1L", categoria="lacteos", ubicacion="nevera", unidad="litros", supermercado="Mercadona", precio_unitario_estimado=0.95, tags=["leche", "lacteos"]),
    LocalBarcode(ean="8400000000117", nombre="Leche semi 1L", categoria="lacteos", ubicacion="nevera", unidad="litros", supermercado="Mercadona", precio_unitario_estimado=0.92, tags=["leche", "lacteos"]),
    LocalBarcode(ean="8400000000124", nombre="Leche desnatada 1L", categoria="lacteos", ubicacion="nevera", unidad="litros", supermercado="Mercadona", precio_unitario_estimado=0.90, tags=["leche", "lacteos"]),
    LocalBarcode(ean="8400000000206", nombre="Huevos camperos M 12u", categoria="lacteos", ubicacion="nevera", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=3.20, tags=["huevos", "proteina"]),
    LocalBarcode(ean="8400000000213", nombre="Huevos XL 12u", categoria="lacteos", ubicacion="nevera", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=3.60, tags=["huevos"]),
    LocalBarcode(ean="8400000000309", nombre="Yogur natural pack 4", categoria="lacteos", ubicacion="nevera", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=1.10, tags=["yogur", "lacteos"]),
    LocalBarcode(ean="8400000000316", nombre="Yogur griego natural", categoria="lacteos", ubicacion="nevera", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=1.30, tags=["yogur", "griego"]),
    LocalBarcode(ean="8400000000402", nombre="Queso fresco 0% 250g", categoria="lacteos", ubicacion="nevera", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=1.45, tags=["queso", "fresco"]),
    LocalBarcode(ean="8400000000419", nombre="Queso en lonchas 200g", categoria="lacteos", ubicacion="nevera", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=2.10, tags=["queso"]),
    LocalBarcode(ean="8400000000505", nombre="Mantequilla 250g", categoria="lacteos", ubicacion="nevera", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=2.00, tags=["mantequilla"]),
    LocalBarcode(ean="8400000000608", nombre="Pan de molde integral", categoria="despensa_seca", ubicacion="despensa", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=1.40, tags=["pan", "integral"]),
    LocalBarcode(ean="8400000000615", nombre="Pan de molde blanco", categoria="despensa_seca", ubicacion="despensa", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=1.25, tags=["pan"]),
    LocalBarcode(ean="8400000000701", nombre="Baguette", categoria="despensa_seca", ubicacion="despensa", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=0.55, tags=["pan"]),
    LocalBarcode(ean="8400000000804", nombre="Arroz redondo 1kg", categoria="despensa_seca", ubicacion="despensa", unidad="kg", supermercado="Mercadona", precio_unitario_estimado=1.35, tags=["arroz", "guarnicion"]),
    LocalBarcode(ean="8400000000811", nombre="Arroz basmati 1kg", categoria="despensa_seca", ubicacion="despensa", unidad="kg", supermercado="Mercadona", precio_unitario_estimado=2.10, tags=["arroz", "basmati"]),
    LocalBarcode(ean="8400000000907", nombre="Pasta espaguetis 500g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=0.95, tags=["pasta"]),
    LocalBarcode(ean="8400000000914", nombre="Pasta macarrones 500g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=0.90, tags=["pasta"]),
    LocalBarcode(ean="8400000000921", nombre="Pasta penne 500g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=0.95, tags=["pasta"]),
    LocalBarcode(ean="8400000001003", nombre="Café molido natural 250g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=2.80, tags=["cafe", "desayuno"]),
    LocalBarcode(ean="8400000001010", nombre="Café en grano 1kg", categoria="despensa_seca", ubicacion="despensa", unidad="kg", supermercado="Mercadona", precio_unitario_estimado=8.50, tags=["cafe"]),
    LocalBarcode(ean="8400000001102", nombre="Café soluble descafeinado 200g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=3.40, tags=["cafe", "descafeinado"]),
    LocalBarcode(ean="8400000001205", nombre="Aceite de oliva virgen extra 1L", categoria="despensa_seca", ubicacion="despensa", unidad="litros", supermercado="Mercadona", precio_unitario_estimado=8.90, tags=["aceite", "aove"]),
    LocalBarcode(ean="8400000001212", nombre="Aceite de oliva suave 1L", categoria="despensa_seca", ubicacion="despensa", unidad="litros", supermercado="Mercadona", precio_unitario_estimado=6.50, tags=["aceite"]),
    LocalBarcode(ean="8400000001308", nombre="Azúcar blanco 1kg", categoria="despensa_seca", ubicacion="despensa", unidad="kg", supermercado="Mercadona", precio_unitario_estimado=1.20, tags=["azucar", "reposteria"]),
    LocalBarcode(ean="8400000001401", nombre="Sal fina 1kg", categoria="despensa_seca", ubicacion="despensa", unidad="kg", supermercado="Mercadona", precio_unitario_estimado=0.60, tags=["sal"]),
    LocalBarcode(ean="8400000001504", nombre="Harina de trigo 1kg", categoria="despensa_seca", ubicacion="despensa", unidad="kg", supermercado="Mercadona", precio_unitario_estimado=0.95, tags=["harina", "reposteria"]),
    LocalBarcode(ean="8400000001607", nombre="Garbanzos cocidos 570g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=1.15, tags=["legumbres", "garbanzos"]),
    LocalBarcode(ean="8400000001614", nombre="Lentejas cocidas 570g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=1.10, tags=["legumbres", "lentejas"]),
    LocalBarcode(ean="8400000001621", nombre="Judías blancas cocidas 570g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=1.15, tags=["legumbres"]),
    LocalBarcode(ean="8400000001700", nombre="Tomate frito 400g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=0.75, tags=["tomate", "salsa"]),
    LocalBarcode(ean="8400000001809", nombre="Atún claro en aceite 3x80g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=2.80, tags=["pescado", "lata"]),
    LocalBarcode(ean="8400000001902", nombre="Galletas María 800g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=1.95, tags=["galletas", "desayuno"]),
    LocalBarcode(ean="8400000002008", nombre="Cereales integrales 500g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=2.40, tags=["cereales", "desayuno"]),
    LocalBarcode(ean="8400000002101", nombre="Mermelada de fresa 350g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=1.80, tags=["mermelada", "desayuno"]),
    LocalBarcode(ean="8400000002204", nombre="Miel 500g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=4.20, tags=["miel", "desayuno"]),
    LocalBarcode(ean="8400000002307", nombre="Chocolate en polvo 400g", categoria="despensa_seca", ubicacion="despensa", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=2.50, tags=["chocolate", "desayuno"]),
    LocalBarcode(ean="8400000002400", nombre="Nata para cocinar 200ml", categoria="lacteos", ubicacion="nevera", unidad="litros", supermercado="Mercadona", precio_unitario_estimado=1.10, tags=["nata", "cocina"]),
    LocalBarcode(ean="8400000002503", nombre="Mantequilla untar 250g", categoria="lacteos", ubicacion="nevera", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=2.15, tags=["mantequilla"]),
    LocalBarcode(ean="8400000002606", nombre="Queso rallado mozzarella 200g", categoria="lacteos", ubicacion="nevera", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=2.00, tags=["queso", "pizza"]),
    LocalBarcode(ean="8400000002709", nombre="Pechuga de pollo 500g", categoria="congelados", ubicacion="congelador", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=4.50, tags=["pollo", "carne"]),
    LocalBarcode(ean="8400000002802", nombre="Merluza congelada 400g", categoria="congelados", ubicacion="congelador", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=4.95, tags=["pescado", "congelado"]),
    LocalBarcode(ean="8400000002905", nombre="Verduras para paella 750g", categoria="congelados", ubicacion="congelador", unidad="gramos", supermercado="Mercadona", precio_unitario_estimado=2.60, tags=["verduras", "congelado"]),
    LocalBarcode(ean="8400000003001", nombre="Pizza congelada 4 quesos", categoria="congelados", ubicacion="congelador", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=2.80, tags=["pizza", "congelado"]),
    LocalBarcode(ean="8400000003104", nombre="Helado vainilla 1L", categoria="congelados", ubicacion="congelador", unidad="litros", supermercado="Mercadona", precio_unitario_estimado=3.50, tags=["helado", "postre"]),
    LocalBarcode(ean="8400000003207", nombre="Detergente líquido 40 lavados", categoria="limpieza", ubicacion="bano", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=5.90, tags=["detergente", "lavanderia"]),
    LocalBarcode(ean="8400000003300", nombre="Suavizante ropa 2L", categoria="limpieza", ubicacion="bano", unidad="litros", supermercado="Mercadona", precio_unitario_estimado=3.40, tags=["suavizante", "lavanderia"]),
    LocalBarcode(ean="8400000003403", nombre="Lejía 2L", categoria="limpieza", ubicacion="bano", unidad="litros", supermercado="Mercadona", precio_unitario_estimado=1.80, tags=["lejia", "desinfectante"]),
    LocalBarcode(ean="8400000003506", nombre="Lavavajillas a mano 750ml", categoria="limpieza", ubicacion="bano", unidad="litros", supermercado="Mercadona", precio_unitario_estimado=1.45, tags=["lavavajillas"]),
    LocalBarcode(ean="8400000003609", nombre="Estropajos 10u", categoria="limpieza", ubicacion="bano", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=1.30, tags=["estropajo"]),
    LocalBarcode(ean="8400000003702", nombre="Papel higiénico 12 rollos", categoria="limpieza", ubicacion="bano", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=4.20, tags=["papel", "bano"]),
    LocalBarcode(ean="8400000003805", nombre="Kleenex 6 cajas", categoria="limpieza", ubicacion="bano", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=4.50, tags=["pañuelos"]),
    LocalBarcode(ean="8400000003908", nombre="Bolsa basura 30L 20u", categoria="limpieza", ubicacion="bano", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=2.10, tags=["basura"]),
    LocalBarcode(ean="8400000004005", nombre="Pilas AA 4u", categoria="recambios_hogar", ubicacion="trastero", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=3.90, tags=["pilas", "electronica"]),
    LocalBarcode(ean="8400000004108", nombre="Bombillas LED E27 6W", categoria="recambios_hogar", ubicacion="trastero", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=5.50, tags=["bombilla", "iluminacion"]),
    LocalBarcode(ean="8400000004201", nombre="Filtro purificador", categoria="recambios_hogar", ubicacion="trastero", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=12.90, tags=["filtro", "agua"]),
    LocalBarcode(ean="8400000004304", nombre="Paracetamol 500mg 20u", categoria="botiquin", ubicacion="bano", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=2.00, tags=["medicamento", "dolor"]),
    LocalBarcode(ean="8400000004407", nombre="Ibuprofeno 600mg 20u", categoria="botiquin", ubicacion="bano", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=2.50, tags=["medicamento", "dolor"]),
    LocalBarcode(ean="8400000004500", nombre="Tiritas 20u", categoria="botiquin", ubicacion="bano", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=1.70, tags=["botiquin", "curas"]),
    LocalBarcode(ean="8400000004603", nombre="Agua oxigenada 250ml", categoria="botiquin", ubicacion="bano", unidad="litros", supermercado="Mercadona", precio_unitario_estimado=1.20, tags=["botiquin", "desinfectante"]),
    LocalBarcode(ean="8400000004706", nombre="Agua mineral 6x1.5L", categoria="despensa_seca", ubicacion="despensa", unidad="litros", supermercado="Mercadona", precio_unitario_estimado=2.40, tags=["agua", "bebida"]),
    LocalBarcode(ean="8400000004809", nombre="Zumo de naranja 1L", categoria="despensa_seca", ubicacion="despensa", unidad="litros", supermercado="Mercadona", precio_unitario_estimado=1.60, tags=["zumo", "desayuno"]),
    LocalBarcode(ean="8400000004902", nombre="Refresco cola 2L", categoria="despensa_seca", ubicacion="despensa", unidad="litros", supermercado="Mercadona", precio_unitario_estimado=1.50, tags=["refresco", "bebida"]),
    LocalBarcode(ean="8400000005006", nombre="Cerveza rubia pack 6", categoria="despensa_seca", ubicacion="despensa", unidad="unidades", supermercado="Mercadona", precio_unitario_estimado=3.60, tags=["cerveza", "bebida"]),
]


def _validar_ean(ean: str) -> None:
    """Lanza ValueError si el EAN no tiene 13 dígitos."""
    if not (ean.isdigit() and len(ean) == 13):
        raise ValueError(f"EAN inválido, debe tener 13 dígitos: {ean}")


class LocalBarcodeManager:
    """CRUD de códigos de barras locales con persistencia JSON."""

    def __init__(self, vault_path: Path | str) -> None:
        self.vault_path = Path(vault_path)
        self._ruta = self.vault_path / "config" / "barcodes.json"
        self._categoria_manager = CategoriaManager(self.vault_path)

    def _validar_categoria(self, categoria: str) -> None:
        """Lanza ValueError si la categoría no existe en el catálogo."""
        if not self._categoria_manager.existe(categoria):
            raise ValueError(f"Categoría no válida: {categoria}")

    def _asegurar_archivo(self) -> None:
        """Crea el archivo con la población inicial si no existe."""
        if self._ruta.exists():
            return
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        self._guardar(list(_BARCODES_INICIALES))

    def _cargar(self) -> list[LocalBarcode]:
        """Carga los códigos de barras locales desde disco."""
        self._asegurar_archivo()
        texto = self._ruta.read_text(encoding="utf-8")
        datos = json.loads(texto)
        return [LocalBarcode.model_validate(b) for b in datos]

    def _guardar(self, barcodes: list[LocalBarcode]) -> None:
        """Persiste la lista completa en disco."""
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        self._ruta.write_text(
            json.dumps(
                [b.model_dump() for b in barcodes],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def listar(self) -> list[LocalBarcode]:
        """Devuelve todos los códigos de barras locales ordenados por EAN."""
        return sorted(self._cargar(), key=lambda b: b.ean)

    def obtener(self, ean: str) -> Optional[LocalBarcode]:
        """Devuelve un código de barras local por su EAN."""
        _validar_ean(ean)
        for b in self._cargar():
            if b.ean == ean:
                return b
        return None

    def crear(self, barcode: LocalBarcode) -> LocalBarcode:
        """Crea un nuevo código de barras local.

        Lanza ValueError si el EAN ya existe o la categoría no es válida.
        """
        _validar_ean(barcode.ean)
        self._validar_categoria(barcode.categoria)
        barcodes = self._cargar()
        if any(b.ean == barcode.ean for b in barcodes):
            raise ValueError(f"EAN ya existe: {barcode.ean}")
        barcodes.append(barcode)
        self._guardar(barcodes)
        return barcode

    def actualizar(self, ean: str, **campos) -> LocalBarcode:
        """Actualiza los campos editables de un código de barras local."""
        _validar_ean(ean)
        if "categoria" in campos:
            self._validar_categoria(campos["categoria"])
        barcodes = self._cargar()
        for b in barcodes:
            if b.ean == ean:
                datos = b.model_dump()
                datos.update(campos)
                actualizado = LocalBarcode.model_validate(datos)
                barcodes = [actualizado if x.ean == ean else x for x in barcodes]
                self._guardar(barcodes)
                return actualizado
        raise KeyError(f"EAN no encontrado: {ean}")

    def borrar(self, ean: str) -> bool:
        """Elimina un código de barras local. Devuelve True si existía."""
        _validar_ean(ean)
        barcodes = self._cargar()
        antes = len(barcodes)
        barcodes = [b for b in barcodes if b.ean != ean]
        if len(barcodes) == antes:
            return False
        self._guardar(barcodes)
        return True
