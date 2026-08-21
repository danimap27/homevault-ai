"""Tests del auto-sync Git del vault (Fase 4)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import git
import pytest

from backend.git_sync import GitSync


@pytest.fixture
def repo_vault(tmp_path: Path) -> git.Repo:
    """Repo git temporal con identidad configurada y un commit inicial."""
    repo = git.Repo.init(tmp_path)
    with repo.config_writer() as cfg:
        cfg.set_value("user", "name", "Test")
        cfg.set_value("user", "email", "test@test.local")
    (tmp_path / "inventario").mkdir()
    (tmp_path / "inventario" / "item.md").write_text("# item\n")
    repo.git.add(A=True)
    repo.index.commit("Inicial")
    return repo


def _mensajes_commits(repo: git.Repo) -> list[str]:
    """Mensajes de commit del repo, del más reciente al más antiguo."""
    return [c.message.strip() for c in repo.iter_commits()]


async def test_schedule_commit_crea_commit_con_skip_ci(
    tmp_path: Path, repo_vault: git.Repo
) -> None:
    """Un cambio programado genera un commit 'Auto-sync: <msg> [skip ci]'."""
    sync = GitSync(tmp_path, debounce_s=0.05, repo=repo_vault)
    (tmp_path / "tareas").mkdir()
    (tmp_path / "tareas" / "t1.md").write_text("# tarea\n")
    sync.schedule_commit("cambio en tareas")
    await sync.flush()
    mensajes = _mensajes_commits(repo_vault)
    assert mensajes[0] == "Auto-sync: cambio en tareas [skip ci]"


async def test_debounce_agrupa_rafagas(tmp_path: Path, repo_vault: git.Repo) -> None:
    """Varios schedule_commit seguidos producen un único commit."""
    sync = GitSync(tmp_path, debounce_s=0.1, repo=repo_vault)
    for i in range(3):
        (tmp_path / "inventario" / "item.md").write_text(f"# item {i}\n")
        sync.schedule_commit(f"cambio {i}")
    await sync.flush()
    mensajes = _mensajes_commits(repo_vault)
    assert len(mensajes) == 2  # Inicial + un solo auto-sync
    assert mensajes[0] == "Auto-sync: cambio 2 [skip ci]"  # último mensaje


async def test_commit_sin_cambios_no_crea_commit(
    tmp_path: Path, repo_vault: git.Repo
) -> None:
    """Si no hay cambios en el working tree no se crea commit vacío."""
    sync = GitSync(tmp_path, debounce_s=0.01, repo=repo_vault)
    sync.schedule_commit("sin cambios")
    await sync.flush()
    assert len(_mensajes_commits(repo_vault)) == 1  # solo el Inicial


async def test_sin_repo_degrada_con_log(tmp_path: Path, caplog) -> None:
    """Un vault sin repo git no rompe: schedule_commit solo registra."""
    sync = GitSync(tmp_path, debounce_s=0.01)
    assert not sync.disponible
    assert "no es un repositorio git" in caplog.text
    sync.schedule_commit("ignorado")
    await sync.flush()  # no lanza excepción


def test_abre_repo_por_defecto_desde_vault_path(
    tmp_path: Path, repo_vault: git.Repo
) -> None:
    """Sin repo inyectado, GitSync abre el repo de vault_path."""
    sync = GitSync(tmp_path)
    assert sync.disponible


class FakeRemote:
    """Fake de remote git: registra los push."""

    def __init__(self) -> None:
        self.pushes = 0

    def push(self) -> None:
        self.pushes += 1


class FakeRepo:
    """Fake mínimo de git.Repo para probar el push opcional."""

    def __init__(self) -> None:
        self.remote_fake = FakeRemote()
        self.commits: list[str] = []
        self.remotes = [self.remote_fake]
        self.git = self

    def add(self, A: bool) -> None:  # noqa: N803 (interfaz de git)
        pass

    def is_dirty(self, untracked_files: bool = False) -> bool:
        return True

    @property
    def index(self) -> "FakeRepo":
        return self

    def commit(self, mensaje: str) -> None:
        self.commits.append(mensaje)

    def remote(self) -> FakeRemote:
        return self.remote_fake


async def test_push_solo_si_remote_enabled(tmp_path: Path) -> None:
    """Con remote_enabled=True se hace push; con False no."""
    repo_on, repo_off = FakeRepo(), FakeRepo()
    sync_on = GitSync(tmp_path, debounce_s=0.01, remote_enabled=True, repo=repo_on)
    sync_off = GitSync(
        tmp_path, debounce_s=0.01, remote_enabled=False, repo=repo_off
    )
    sync_on.schedule_commit("con push")
    sync_off.schedule_commit("sin push")
    await asyncio.gather(sync_on.flush(), sync_off.flush())
    assert repo_on.remote_fake.pushes == 1
    assert repo_on.commits == ["Auto-sync: con push [skip ci]"]
    assert repo_off.remote_fake.pushes == 0
    assert repo_off.commits == ["Auto-sync: sin push [skip ci]"]
