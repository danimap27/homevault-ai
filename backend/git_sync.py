"""Auto-sincronización Git del vault (Fase 4).

GitSync agrupa ráfagas de cambios con un debounce configurable y crea
commits automáticos "Auto-sync: <mensaje> [skip ci]", con push opcional
al remote del propio repo si GIT_REMOTE_ENABLED=true. Si el vault no es
un repositorio git, degrada con log sin romper el resto del sistema.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import git
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

logger = logging.getLogger(__name__)


class GitSync:
    """Commits automáticos con debounce sobre el repositorio del vault.

    El repo es inyectable (tests con repos temporales o fakes); si no se
    pasa, se abre vault_path con GitPython. Todas las operaciones git se
    ejecutan en un hilo para no bloquear el bucle asyncio.
    """

    def __init__(
        self,
        vault_path: Path | str,
        debounce_s: float = 5.0,
        remote_enabled: bool = False,
        repo: Optional[git.Repo] = None,
    ) -> None:
        self.vault_path = Path(vault_path)
        self.debounce_s = debounce_s
        self.remote_enabled = remote_enabled
        self._tarea_pendiente: Optional[asyncio.Task] = None
        if repo is not None:
            self._repo: Optional[git.Repo] = repo
        else:
            self._repo = self._abrir_repo(self.vault_path)

    @staticmethod
    def _abrir_repo(vault_path: Path) -> Optional[git.Repo]:
        """Abre el repo git del vault, degradando a None si no existe."""
        try:
            return git.Repo(vault_path)
        except (InvalidGitRepositoryError, NoSuchPathError):
            logger.warning(
                "El vault %s no es un repositorio git; auto-sync desactivado",
                vault_path,
            )
            return None

    @property
    def disponible(self) -> bool:
        """True si hay un repo git operativo sobre el vault."""
        return self._repo is not None

    def schedule_commit(self, mensaje: str) -> None:
        """Programa un commit tras el debounce, agrupando ráfagas.

        Cada llamada cancela el commit pendiente anterior y reprograma, de
        modo que una ráfaga de cambios genera un único commit con el
        último mensaje. Sin repo git solo se registra en el log.
        """
        if self._repo is None:
            logger.debug("schedule_commit ignorado (sin repo git): %s", mensaje)
            return
        if self._tarea_pendiente is not None:
            self._tarea_pendiente.cancel()
        self._tarea_pendiente = asyncio.create_task(
            self._commit_tras_debounce(mensaje)
        )

    async def flush(self) -> None:
        """Espera al commit pendiente (útil en tests y en el apagado)."""
        tarea = self._tarea_pendiente
        if tarea is not None:
            try:
                await tarea
            except asyncio.CancelledError:
                pass

    async def _commit_tras_debounce(self, mensaje: str) -> None:
        """Espera el debounce y ejecuta el commit (cancelable)."""
        await asyncio.sleep(self.debounce_s)
        await self._commit(mensaje)
        self._tarea_pendiente = None

    async def _commit(self, mensaje: str) -> None:
        """Ejecuta el commit (y push opcional) fuera del bucle asyncio."""
        try:
            await asyncio.to_thread(self._commit_sync, mensaje)
        except GitCommandError:
            logger.exception("Error git al auto-sincronizar: %s", mensaje)
        except Exception:
            logger.exception("Error inesperado en GitSync: %s", mensaje)

    def _commit_sync(self, mensaje: str) -> None:
        """Commit síncrono: add de todo, commit [skip ci] y push opcional."""
        assert self._repo is not None
        self._repo.git.add(A=True)
        if not self._repo.is_dirty(untracked_files=False):
            logger.debug("Sin cambios que commitear: %s", mensaje)
            return
        self._repo.index.commit(f"Auto-sync: {mensaje} [skip ci]")
        logger.info("Auto-sync commit: %s", mensaje)
        if self.remote_enabled and self._repo.remotes:
            self._repo.remote().push()
            logger.info("Auto-sync push completado")
