"""Gestión dinámica de categorías de consumibles de HomeVault AI.

Las categorías se persisten en ``vault/config/categorias.json``. Si el archivo
no existe, se cargan las 6 categorías originales de la Fase 1 con nombres
legibles, colores e iconos por defecto. El modelo sigue siendo retrocompatible
con los archivos Markdown existentes: la categoría se almacena como un
``str`` libre y este módulo actúa como catálogo de valores permitidos.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from backend.models import Ubicacion


# --- Categorías por defecto (retrocompatibles con la Fase 1) -----------------

_CATEGORIAS_POR_DEFECTO: list[dict] = [
    {
        "id": "lacteos",
        "nombre": "Lácteos",
        "color": "#3b82f6",
        "icono": "🥛",
        "ubicacion_default": "nevera",
        "orden": 0,
    },
    {
        "id": "congelados",
        "nombre": "Congelados",
        "color": "#06b6d4",
        "icono": "🧊",
        "ubicacion_default": "congelador",
        "orden": 1,
    },
    {
        "id": "despensa_seca",
        "nombre": "Despensa seca",
        "color": "#f59e0b",
        "icono": "🥫",
        "ubicacion_default": "despensa",
        "orden": 2,
    },
    {
        "id": "limpieza",
        "nombre": "Limpieza",
        "color": "#10b981",
        "icono": "🧽",
        "ubicacion_default": "bano",
        "orden": 3,
    },
    {
        "id": "recambios_hogar",
        "nombre": "Recambios del hogar",
        "color": "#8b5cf6",
        "icono": "🔧",
        "ubicacion_default": "trastero",
        "orden": 4,
    },
    {
        "id": "botiquin",
        "nombre": "Botiquín",
        "color": "#ef4444",
        "icono": "💊",
        "ubicacion_default": "bano",
        "orden": 5,
    },
]


# --- Modelo Pydantic ---------------------------------------------------------


class Categoria(BaseModel):
    """Categoría personalizable de un ítem de inventario."""

    id: str
    nombre: str
    color: str = "#6366f1"
    icono: str = "📦"
    ubicacion_default: Ubicacion = "despensa"
    orden: int = Field(default=0, ge=0)

    @field_validator("color")
    @classmethod
    def _validar_color_hex(cls, valor: str) -> str:
        """Exige un color hexadecimal de 6 dígitos."""
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", valor):
            raise ValueError(f"El color debe ser un HEX de 6 dígitos: {valor}")
        return valor


# --- Manager -----------------------------------------------------------------


def _slugificar(texto: str) -> str:
    """Convierte un nombre en un slug ASCII seguro para usar como id."""
    normalizado = unicodedata.normalize("NFKD", texto)
    ascii_str = normalizado.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_str.lower()).strip("_")
    return slug or "categoria"


class CategoriaManager:
    """CRUD de categorías con persistencia JSON bajo ``vault/config/``."""

    def __init__(self, vault_path: Path | str) -> None:
        self.vault_path = Path(vault_path)
        self._ruta = self.vault_path / "config" / "categorias.json"

    def _asegurar_archivo(self) -> None:
        """Crea el archivo con las categorías por defecto si no existe."""
        if self._ruta.exists():
            return
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        self._guardar([Categoria.model_validate(c) for c in _CATEGORIAS_POR_DEFECTO])

    def _cargar(self) -> list[Categoria]:
        """Carga las categorías desde disco."""
        self._asegurar_archivo()
        texto = self._ruta.read_text(encoding="utf-8")
        datos = json.loads(texto)
        return [Categoria.model_validate(c) for c in datos]

    def _guardar(self, categorias: list[Categoria]) -> None:
        """Persiste la lista completa de categorías en disco."""
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        self._ruta.write_text(
            json.dumps(
                [c.model_dump() for c in categorias],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def listar(self) -> list[Categoria]:
        """Devuelve todas las categorías ordenadas por ``orden`` y nombre."""
        return sorted(self._cargar(), key=lambda c: (c.orden, c.nombre.casefold()))

    def obtener(self, id: str) -> Optional[Categoria]:
        """Devuelve una categoría por su id o ``None`` si no existe."""
        for c in self._cargar():
            if c.id == id:
                return c
        return None

    def existe(self, id: str) -> bool:
        """Indica si existe una categoría con el id indicado."""
        return self.obtener(id) is not None

    def crear(
        self,
        nombre: str,
        id: Optional[str] = None,
        color: Optional[str] = None,
        icono: Optional[str] = None,
        ubicacion_default: Optional[str] = None,
        orden: Optional[int] = None,
    ) -> Categoria:
        """Crea una nueva categoría.

        Args:
            nombre: Nombre legible de la categoría.
            id: Slug opcional; si no se indica se deriva del nombre.
            color: Color HEX de 6 dígitos (por defecto ``#6366f1``).
            icono: Emoji o identificador de icono.
            ubicacion_default: Ubicación por defecto para ítems de esta
                categoría (debe ser una ``Ubicacion`` válida).
            orden: Posición en la lista (>= 0).

        Raises:
            ValueError: si el id ya existe, el color no es HEX válido o la
                ubicación no está entre las permitidas.
        """
        categoria_id = id if id is not None else _slugificar(nombre)
        categorias = self._cargar()
        if any(c.id == categoria_id for c in categorias):
            raise ValueError(f"La categoría '{categoria_id}' ya existe")

        ubicacion: Ubicacion = (
            ubicacion_default if ubicacion_default is not None else "despensa"
        )
        if ubicacion not in ("nevera", "congelador", "despensa", "bano", "trastero"):
            raise ValueError(f"Ubicación por defecto no válida: {ubicacion}")

        nueva = Categoria(
            id=categoria_id,
            nombre=nombre,
            color=color if color is not None else "#6366f1",
            icono=icono if icono is not None else "📦",
            ubicacion_default=ubicacion,
            orden=orden if orden is not None else 0,
        )
        categorias.append(nueva)
        self._guardar(categorias)
        return nueva

    def actualizar(
        self,
        id: str,
        nombre: Optional[str] = None,
        color: Optional[str] = None,
        icono: Optional[str] = None,
        ubicacion_default: Optional[str] = None,
        orden: Optional[int] = None,
    ) -> Categoria:
        """Actualiza los campos editables de una categoría.

        Raises:
            KeyError: si la categoría no existe.
            ValueError: si el color o la ubicación no son válidos.
        """
        categorias = self._cargar()
        for c in categorias:
            if c.id == id:
                if nombre is not None:
                    c.nombre = nombre
                if color is not None:
                    c.color = Categoria.model_validate(
                        {"id": id, "nombre": c.nombre, "color": color}
                    ).color
                if icono is not None:
                    c.icono = icono
                if ubicacion_default is not None:
                    if ubicacion_default not in (
                        "nevera",
                        "congelador",
                        "despensa",
                        "bano",
                        "trastero",
                    ):
                        raise ValueError(
                            f"Ubicación por defecto no válida: {ubicacion_default}"
                        )
                    c.ubicacion_default = ubicacion_default  # type: ignore[assignment]
                if orden is not None:
                    c.orden = orden
                self._guardar(categorias)
                return c
        raise KeyError(f"Categoría no encontrada: {id}")

    def borrar(self, id: str) -> bool:
        """Elimina una categoría. Devuelve ``True`` si existía.

        Note:
            La comprobación de ítems en uso se realiza en ``VaultManager`` o
            en los endpoints de la API para mantener este módulo independiente
            del esquema de consumibles.
        """
        categorias = self._cargar()
        antes = len(categorias)
        categorias = [c for c in categorias if c.id != id]
        if len(categorias) == antes:
            return False
        self._guardar(categorias)
        return True
