"""Gestión de supermercados de HomeVault AI.

Los supermercados se persisten en ``vault/config/supermercados.json``. Solo
uno puede estar marcado como predeterminado; las operaciones de escritura
mantienen esa invariante automáticamente.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class Supermercado(BaseModel):
    """Supermercado donde se realizan las compras."""

    id: str
    nombre: str
    predeterminado: bool = False


class SupermercadoManager:
    """CRUD de supermercados con persistencia JSON."""

    _PREDETERMINADO_POR_DEFECTO: str = "mercadona"

    def __init__(self, vault_path: Path | str) -> None:
        self.vault_path = Path(vault_path)
        self._ruta = self.vault_path / "config" / "supermercados.json"

    def _asegurar_archivo(self) -> None:
        """Crea el archivo por defecto si no existe."""
        if self._ruta.exists():
            return
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        self._guardar(
            [
                Supermercado(
                    id=self._PREDETERMINADO_POR_DEFECTO,
                    nombre="Mercadona",
                    predeterminado=True,
                )
            ]
        )

    def _cargar(self) -> list[Supermercado]:
        """Carga la lista de supermercados desde disco."""
        self._asegurar_archivo()
        texto = self._ruta.read_text(encoding="utf-8")
        datos = json.loads(texto)
        return [Supermercado.model_validate(s) for s in datos]

    def _guardar(self, supermercados: list[Supermercado]) -> None:
        """Persiste la lista completa en disco."""
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        self._ruta.write_text(
            json.dumps(
                [s.model_dump() for s in supermercados],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _slugificar(nombre: str) -> str:
        """Genera un slug ASCII a partir del nombre."""
        normalizado = unicodedata.normalize("NFKD", nombre)
        ascii_str = normalizado.encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-z0-9]+", "_", ascii_str.lower()).strip("_")
        return slug or "supermercado"

    def listar(self) -> list[Supermercado]:
        """Devuelve todos los supermercados ordenados por nombre."""
        return sorted(self._cargar(), key=lambda s: s.nombre.casefold())

    def crear(self, nombre: str) -> Supermercado:
        """Crea un nuevo supermercado.

        El primer supermercado creado pasa a ser el predeterminado.
        """
        supermercados = self._cargar()
        slug = self._slugificar(nombre)
        item_id = slug
        contador = 1
        while any(s.id == item_id for s in supermercados):
            item_id = f"{slug}_{contador}"
            contador += 1
        nuevo = Supermercado(id=item_id, nombre=nombre)
        if not supermercados:
            nuevo.predeterminado = True
        supermercados.append(nuevo)
        self._guardar(supermercados)
        return nuevo

    def actualizar(
        self,
        item_id: str,
        nombre: Optional[str] = None,
        predeterminado: Optional[bool] = None,
    ) -> Supermercado:
        """Actualiza un supermercado existente.

        Si se marca uno como predeterminado, el resto pierde la marca.
        """
        supermercados = self._cargar()
        encontrado = next((s for s in supermercados if s.id == item_id), None)
        if encontrado is None:
            raise KeyError(f"Supermercado no encontrado: {item_id}")
        if nombre is not None:
            encontrado.nombre = nombre
        if predeterminado is not None:
            if predeterminado:
                for s in supermercados:
                    s.predeterminado = False
            encontrado.predeterminado = predeterminado
        self._guardar(supermercados)
        return encontrado

    def borrar(self, item_id: str) -> bool:
        """Elimina un supermercado. Devuelve True si existía."""
        supermercados = self._cargar()
        antes = len(supermercados)
        supermercados = [s for s in supermercados if s.id != item_id]
        if len(supermercados) == antes:
            return False
        # Si el borrado dejaba la lista vacía o sin predeterminado, saneamos
        if supermercados and not any(s.predeterminado for s in supermercados):
            supermercados[0].predeterminado = True
        self._guardar(supermercados)
        return True

    def obtener_predeterminado(self) -> Optional[Supermercado]:
        """Devuelve el supermercado marcado como predeterminado."""
        for s in self._cargar():
            if s.predeterminado:
                return s
        return None
