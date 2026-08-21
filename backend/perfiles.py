"""Gestor de perfiles de usuario estilo Netflix para HomeVault AI.

Persiste los perfiles en ``vault/config/perfiles.json``. Si el archivo no
existe, crea automáticamente un perfil por defecto llamado "Yo".
"""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from typing import Optional

from backend.models import Perfil

_MAX_PERFILES = 8

_PALETA_COLORES = [
    "#ef4444",
    "#f97316",
    "#f59e0b",
    "#84cc16",
    "#10b981",
    "#06b6d4",
    "#3b82f6",
    "#6366f1",
    "#8b5cf6",
    "#d946ef",
    "#f43f5e",
]


class PerfilManager:
    """Gestor CRUD de perfiles con persistencia en JSON.

    Los métodos son asíncronos para mantener la misma interfaz que
    ``VaultManager``, aunque internamente trabajen sobre un archivo local.
    """

    def __init__(self, vault_path: Path | str) -> None:
        self.vault_path = Path(vault_path)
        self._ruta = self.vault_path / "config" / "perfiles.json"

    def _ruta_config(self) -> Path:
        """Devuelve la ruta al JSON de perfiles."""
        return self._ruta

    async def _cargar(self) -> list[Perfil]:
        """Carga los perfiles desde el JSON, creando el perfil por defecto si falta."""
        if not self._ruta.exists():
            await self._guardar([self._perfil_por_defecto()])

        def _leer() -> list[Perfil]:
            texto = self._ruta.read_text(encoding="utf-8")
            datos = json.loads(texto)
            return [Perfil.model_validate(p) for p in datos]

        return await asyncio.to_thread(_leer)

    async def _guardar(self, perfiles: list[Perfil]) -> None:
        """Guarda la lista de perfiles en el JSON con indentación."""
        self._ruta.parent.mkdir(parents=True, exist_ok=True)

        def _escribir() -> None:
            datos = [p.model_dump(mode="json") for p in perfiles]
            self._ruta.write_text(
                json.dumps(datos, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        await asyncio.to_thread(_escribir)

    @staticmethod
    def _perfil_por_defecto() -> Perfil:
        """Perfil inicial creado cuando no existe configuración."""
        return Perfil(
            id="yo",
            nombre="Yo",
            avatar="👤",
            color=random.choice(_PALETA_COLORES),
        )

    async def listar(self) -> list[Perfil]:
        """Devuelve todos los perfiles ordenados por id."""
        perfiles = await self._cargar()
        return sorted(perfiles, key=lambda p: p.id)

    async def obtener(self, perfil_id: str) -> Optional[Perfil]:
        """Busca un perfil por su id."""
        perfiles = await self._cargar()
        for perfil in perfiles:
            if perfil.id == perfil_id:
                return perfil
        return None

    async def crear(
        self,
        perfil_id: str,
        nombre: str,
        avatar: str = "👤",
        color: Optional[str] = None,
        pin: Optional[str] = None,
        preferencias: Optional[dict] = None,
    ) -> Perfil:
        """Crea un nuevo perfil validando restricciones de negocio.

        Raises:
            ValueError: si se superan 8 perfiles, el id ya existe,
                el nombre está vacío o el PIN no tiene 4 dígitos.
        """
        perfiles = await self._cargar()

        if len(perfiles) >= _MAX_PERFILES:
            raise ValueError(f"No se pueden crear más de {_MAX_PERFILES} perfiles")
        if any(p.id == perfil_id for p in perfiles):
            raise ValueError(f"El id de perfil ya existe: {perfil_id}")
        if not nombre or not nombre.strip():
            raise ValueError("El nombre del perfil no puede estar vacío")
        if pin is not None and pin != "" and not pin.isdigit() and len(pin) != 4:
            raise ValueError("El PIN debe tener exactamente 4 dígitos")

        perfil = Perfil(
            id=perfil_id,
            nombre=nombre.strip(),
            avatar=avatar,
            color=color or random.choice(_PALETA_COLORES),
            pin=pin if pin else None,
            preferencias=preferencias or {},
        )
        perfiles.append(perfil)
        await self._guardar(perfiles)
        return perfil

    async def actualizar(
        self,
        perfil_id: str,
        nombre: Optional[str] = None,
        avatar: Optional[str] = None,
        color: Optional[str] = None,
        pin: Optional[str] = None,
        preferencias: Optional[dict] = None,
    ) -> Perfil:
        """Actualiza los campos editables de un perfil existente.

        Raises:
            KeyError: si el perfil no existe.
            ValueError: si el nombre está vacío o el PIN es inválido.
        """
        perfiles = await self._cargar()
        for perfil in perfiles:
            if perfil.id == perfil_id:
                if nombre is not None:
                    if not nombre.strip():
                        raise ValueError(
                            "El nombre del perfil no puede estar vacío"
                        )
                    perfil.nombre = nombre.strip()
                if avatar is not None:
                    perfil.avatar = avatar
                if color is not None:
                    perfil.color = color
                if pin is not None:
                    if pin != "" and (not pin.isdigit() or len(pin) != 4):
                        raise ValueError(
                            "El PIN debe tener exactamente 4 dígitos"
                        )
                    perfil.pin = pin if pin else None
                if preferencias is not None:
                    perfil.preferencias = preferencias
                await self._guardar(perfiles)
                return perfil
        raise KeyError(f"Perfil no encontrado: {perfil_id}")

    async def borrar(self, perfil_id: str) -> None:
        """Elimina un perfil si no es el último.

        Raises:
            KeyError: si el perfil no existe.
            ValueError: si se intenta borrar el único perfil restante.
        """
        perfiles = await self._cargar()
        if len(perfiles) <= 1:
            raise ValueError("No se puede eliminar el último perfil")
        nuevos = [p for p in perfiles if p.id != perfil_id]
        if len(nuevos) == len(perfiles):
            raise KeyError(f"Perfil no encontrado: {perfil_id}")
        await self._guardar(nuevos)

    async def verificar_pin(self, perfil_id: str, pin: str) -> bool:
        """Devuelve True si el PIN coincide o si el perfil no tiene PIN.

        Raises:
            KeyError: si el perfil no existe.
        """
        perfil = await self.obtener(perfil_id)
        if perfil is None:
            raise KeyError(f"Perfil no encontrado: {perfil_id}")
        if not perfil.pin:
            return True
        return perfil.pin == pin
