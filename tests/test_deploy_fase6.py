"""Tests de Fase 6: artefactos de despliegue y templates del vault.

Validan el docker-compose.yml, el Dockerfile del backend, la configuración
de Mosquitto y que los templates Obsidian de vault/_templates/ parsean
contra los modelos Pydantic (misma ruta que VaultManager).
"""

from pathlib import Path

import frontmatter
import pytest
import yaml

from backend.models import Consumible, PlanSemanal, Receta, Tarea

RAIZ = Path(__file__).resolve().parent.parent
COMPOSE = RAIZ / "docker-compose.yml"
DOCKERFILE = RAIZ / "backend" / "Dockerfile"
MOSQUITTO_CONF = RAIZ / "mosquitto" / "mosquitto.conf"
TEMPLATES = RAIZ / "vault" / "_templates"


# --- docker-compose.yml ------------------------------------------------------


@pytest.fixture(scope="module")
def compose() -> dict:
    with COMPOSE.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_compose_yaml_valido(compose: dict) -> None:
    assert isinstance(compose, dict)
    assert "services" in compose


def test_compose_servicios_esperados(compose: dict) -> None:
    assert set(compose["services"]) == {"backend", "frontend", "mqtt"}


def test_compose_backend(compose: dict) -> None:
    backend = compose["services"]["backend"]
    assert backend["env_file"] == ".env"
    volumenes = backend["volumes"]
    assert "./vault:/app/vault" in volumenes
    assert "./credentials:/app/credentials" in volumenes
    assert "8080:8080" in backend["ports"]


def test_compose_frontend_depends_on_backend(compose: dict) -> None:
    frontend = compose["services"]["frontend"]
    assert "3000:3000" in frontend["ports"]
    assert "backend" in frontend["depends_on"]


def test_compose_mqtt_sin_puertos_publicados(compose: dict) -> None:
    mqtt = compose["services"]["mqtt"]
    assert mqtt["image"] == "eclipse-mosquitto:2"
    # El broker es solo de red interna: no debe exponer 1883 al host.
    assert "ports" not in mqtt
    volumenes = " ".join(mqtt["volumes"])
    assert "mosquitto.conf" in volumenes


def test_compose_red_compartida(compose: dict) -> None:
    redes = compose["networks"]
    assert redes, "debe existir al menos una red"
    for servicio in compose["services"].values():
        assert servicio.get("networks"), "todo servicio usa la red interna"


# --- Dockerfile del backend ---------------------------------------------------


def test_dockerfile_backend() -> None:
    contenido = DOCKERFILE.read_text(encoding="utf-8")
    assert "python:3.11-slim" in contenido
    assert "pip install" in contenido
    assert "uvicorn" in contenido
    assert "backend.main:app" in contenido
    assert "0.0.0.0" in contenido and "8080" in contenido


# --- Mosquitto ----------------------------------------------------------------


def test_mosquitto_conf() -> None:
    lineas = [
        ln.split("#")[0].strip()
        for ln in MOSQUITTO_CONF.read_text(encoding="utf-8").splitlines()
        if ln.split("#")[0].strip()
    ]
    assert "listener 1883" in lineas
    assert "allow_anonymous true" in lineas
    assert "persistence true" in lineas


# --- Templates Obsidian -------------------------------------------------------


def _metadata_template(nombre: str) -> dict:
    post = frontmatter.load(TEMPLATES / nombre)
    return dict(post.metadata)


def test_templates_existen() -> None:
    for nombre in ("consumible.md", "receta.md", "tarea.md", "plan-semanal.md"):
        assert (TEMPLATES / nombre).is_file(), nombre


def test_template_consumible_valida_contra_modelo() -> None:
    meta = _metadata_template("consumible.md")
    meta["id"] = "item_test"
    meta["nombre"] = "Prueba"
    item = Consumible.model_validate(meta)
    assert item.categoria and item.unidad


def test_template_receta_valida_contra_modelo() -> None:
    meta = _metadata_template("receta.md")
    meta["id"] = "recipe_test"
    meta["titulo"] = "Prueba"
    receta = Receta.model_validate(meta)
    assert len(receta.ingredientes) == 1


def test_template_tarea_valida_contra_modelo() -> None:
    meta = _metadata_template("tarea.md")
    meta["id"] = "task_test"
    meta["titulo"] = "Prueba"
    tarea = Tarea.model_validate(meta)
    assert tarea.estado == "pendiente"


def test_template_plan_semanal_valida_contra_modelo() -> None:
    meta = _metadata_template("plan-semanal.md")
    plan = PlanSemanal.model_validate(meta)
    assert len(plan.dias) == 7
    assert "lunes" in plan.dias and "domingo" in plan.dias


def test_claves_templates_cubren_campos_modelo() -> None:
    """Cada template declara TODOS los campos del esquema correspondiente."""
    casos = {
        "consumible.md": set(Consumible.model_fields),
        "receta.md": set(Receta.model_fields),
        "tarea.md": set(Tarea.model_fields),
        "plan-semanal.md": set(PlanSemanal.model_fields),
    }
    for nombre, campos_modelo in casos.items():
        claves_template = set(_metadata_template(nombre))
        faltan = campos_modelo - claves_template
        assert not faltan, f"{nombre}: faltan {faltan}"
