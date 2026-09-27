"""Tests del posponer tareas (snooze), del chat del hogar y de /api/insights."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from backend.ai_chat import HomeChat
from backend.main import app
from backend.vault_manager import VaultManager
from conftest import FakeLLM, escribir_md, metadata_tarea_base


@pytest.fixture
def cliente(vault_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient de la app completa con el vault temporal."""
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    with TestClient(app) as cliente:
        yield cliente


# --- Snooze --------------------------------------------------------------------


def test_snooze_desde_fecha_pasada_mueve_a_hoy_mas_dias(
    cliente: TestClient, vault_path: Path
) -> None:
    ayer = (date.today() - timedelta(days=1)).isoformat()
    escribir_md(
        vault_path, "tareas", "bano.md", metadata_tarea_base(fecha_programada=ayer)
    )
    respuesta = cliente.post(
        "/api/tasks/tarea_test_01/snooze", json={"dias": 3}
    )
    assert respuesta.status_code == 200
    esperado = (date.today() + timedelta(days=3)).isoformat()
    assert respuesta.json()["fecha_programada"] == esperado


def test_snooze_sin_fecha_usa_hoy(
    cliente: TestClient, vault_path: Path
) -> None:
    escribir_md(
        vault_path, "tareas", "bano.md", metadata_tarea_base(fecha_programada=None)
    )
    respuesta = cliente.post("/api/tasks/tarea_test_01/snooze", json={"dias": 1})
    assert respuesta.status_code == 200
    assert respuesta.json()["fecha_programada"] == (
        date.today() + timedelta(days=1)
    ).isoformat()


def test_snooze_respeta_fecha_futura(cliente: TestClient, vault_path: Path) -> None:
    futuro = (date.today() + timedelta(days=10)).isoformat()
    escribir_md(
        vault_path, "tareas", "bano.md", metadata_tarea_base(fecha_programada=futuro)
    )
    respuesta = cliente.post("/api/tasks/tarea_test_01/snooze", json={"dias": 2})
    assert respuesta.status_code == 200
    assert respuesta.json()["fecha_programada"] == (
        date.today() + timedelta(days=12)
    ).isoformat()


def test_snooze_tarea_inexistente(cliente: TestClient) -> None:
    respuesta = cliente.post("/api/tasks/no_existe/snooze", json={"dias": 1})
    assert respuesta.status_code == 404


def test_snooze_dias_invalidos(cliente: TestClient, vault_path: Path) -> None:
    escribir_md(vault_path, "tareas", "bano.md", metadata_tarea_base())
    respuesta = cliente.post("/api/tasks/tarea_test_01/snooze", json={"dias": 0})
    assert respuesta.status_code == 422


# --- Chat del hogar -------------------------------------------------------------


async def test_chat_contexto_incluye_datos(vault_poblado: VaultManager) -> None:
    """El contexto resume inventario, lista de compra y tareas pendientes."""
    (vault_poblado.vault_path / "listas" / "compra.md").write_text(
        "# Lista de la compra\n\n- [ ] Detergente <!-- item_id:item_det; cantidad:1.0; unidad:unidades; categoria:limpieza -->\n",
        encoding="utf-8",
    )
    tarea = {
        "id": "tarea_ctx",
        "titulo": "Regar las plantas",
        "frecuencia": "semanal",
        "estado": "pendiente",
        "prioridad": "baja",
        "fecha_programada": "2026-09-27",
    }
    escribir_md(vault_poblado.vault_path, "tareas", "plantas.md", tarea)

    chat = HomeChat(vault_poblado, FakeLLM())
    contexto, n_items, n_tareas = await chat.construir_contexto()

    assert "Yogur natural" in contexto
    assert "Detergente" in contexto
    assert "Regar las plantas" in contexto
    assert n_items == 2
    assert n_tareas == 1


async def test_chat_responde_con_llm(vault_poblado: VaultManager) -> None:
    llm = FakeLLM(["Tienes 6 yogures en la nevera."])
    chat = HomeChat(vault_poblado, llm)
    respuesta = await chat.responder("¿Cuántos yogures tengo?")
    assert respuesta.respuesta == "Tienes 6 yogures en la nevera."
    assert respuesta.items_en_contexto == 2
    # El prompt enviado incluye el contexto del hogar y la pregunta
    prompt = llm.llamadas[0]["prompt"]
    assert "Yogur natural" in prompt
    assert "¿Cuántos yogures tengo?" in prompt


def test_endpoint_chat_ok(cliente: TestClient, vault: VaultManager) -> None:
    """El endpoint usa el HomeChat del estado de la app (LLM inyectable)."""
    llm = FakeLLM(["No queda leche, añádela a la compra."])
    cliente.app.state.home_chat = HomeChat(vault, llm)  # type: ignore[attr-defined]
    respuesta = cliente.post("/api/ai/chat", json={"mensaje": "¿queda leche?"})
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["respuesta"] == "No queda leche, añádela a la compra."


def test_endpoint_chat_sin_asistente(cliente: TestClient) -> None:
    cliente.app.state.home_chat = None  # type: ignore[attr-defined]
    respuesta = cliente.post("/api/ai/chat", json={"mensaje": "hola"})
    assert respuesta.status_code == 503


def test_endpoint_chat_mensaje_vacio(cliente: TestClient) -> None:
    respuesta = cliente.post("/api/ai/chat", json={"mensaje": ""})
    assert respuesta.status_code == 422


# --- /api/insights ---------------------------------------------------------------


def test_endpoint_insights_vacio(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/insights")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["total_items"] == 0
    assert datos["reposicion"] == []
    assert datos["tareas"]["pendientes"] == 0
    assert datos["desperdicio_mes"]["total_registros"] == 0


def test_endpoint_insights_con_datos(
    cliente: TestClient, vault_path: Path
) -> None:
    escribir_md(
        vault_path,
        "inventario/limpieza",
        "lejia.md",
        {
            "id": "item_lejia",
            "nombre": "Lejía concentrada",
            "categoria": "limpieza",
            "ubicacion": "bano",
            "stock_actual": 0.0,
            "stock_minimo": 1.0,
            "unidad": "unidades",
            "precio_unitario_estimado": 1.2,
            # Señal de uso: si no, el motor lo trataría como placeholder
            "ultimo_consumo": "2026-09-01T10:00:00Z",
        },
    )
    escribir_md(
        vault_path,
        "tareas",
        "vencida.md",
        metadata_tarea_base(fecha_programada="2020-01-01"),
    )

    respuesta = cliente.get("/api/insights")
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["total_items"] == 1
    assert datos["items_bajo_minimo"] == 1
    assert datos["valor_inventario"] == 0.0
    assert len(datos["reposicion"]) == 1
    assert datos["reposicion"][0]["urgencia"] == "critica"
    assert datos["tareas"]["vencidas"] == 1

    restock = cliente.get("/api/insights/restock")
    assert restock.status_code == 200
    assert restock.json()[0]["item_id"] == "item_lejia"

    stats = cliente.get("/api/insights/tasks")
    assert stats.status_code == 200
    assert stats.json()["vencidas"] == 1

    predicciones = cliente.get("/api/insights/predictions")
    assert predicciones.status_code == 200
    assert predicciones.json() == []


# --- Streaming del asistente (SSE) -------------------------------------------


class FakeLLMStream:
    """Fake del ClienteLLM con soporte de streaming por trozos."""

    def __init__(self, trozos: list[str]) -> None:
        self.trozos = trozos

    async def completar(
        self,
        prompt: str,
        imagen: bytes | None = None,
        mime_type: str | None = None,
    ) -> str:
        return "".join(self.trozos)

    async def completar_stream(self, prompt: str):
        for trozo in self.trozos:
            yield trozo


async def test_responder_stream_emite_eventos(
    vault_poblado: VaultManager,
) -> None:
    chat = HomeChat(vault_poblado, FakeLLMStream(["Hola ", "mundo"]))
    eventos = [evento async for evento in chat.responder_stream("¿qué hay?")]
    assert eventos[0]["tipo"] == "meta"
    assert eventos[0]["items"] >= 1
    assert eventos[-1]["tipo"] == "fin"
    tokens = [e["texto"] for e in eventos if e["tipo"] == "token"]
    assert "".join(tokens) == "Hola mundo"


async def test_responder_stream_fallback_sin_stream(
    vault_poblado: VaultManager,
) -> None:
    """Un cliente sin ``completar_stream`` emite la respuesta como un token."""
    chat = HomeChat(vault_poblado, FakeLLM(["Respuesta completa."]))
    eventos = [evento async for evento in chat.responder_stream("hola")]
    tokens = [e["texto"] for e in eventos if e["tipo"] == "token"]
    assert tokens == ["Respuesta completa."]
    assert eventos[-1]["tipo"] == "fin"


def test_endpoint_chat_stream(
    cliente: TestClient, vault_poblado: VaultManager
) -> None:
    cliente.app.state.home_chat = HomeChat(  # type: ignore[attr-defined]
        vault_poblado, FakeLLMStream(["Tienes ", "6 yogures."])
    )
    respuesta = cliente.post("/api/ai/chat/stream", json={"mensaje": "¿yogures?"})
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/event-stream")
    assert '"tipo": "meta"' in respuesta.text
    assert "Tienes " in respuesta.text
    assert "6 yogures." in respuesta.text
    assert '"tipo": "fin"' in respuesta.text


def test_endpoint_chat_stream_503_sin_asistente(cliente: TestClient) -> None:
    cliente.app.state.home_chat = None  # type: ignore[attr-defined]
    respuesta = cliente.post("/api/ai/chat/stream", json={"mensaje": "hola"})
    assert respuesta.status_code == 503


# --- Jobs del asistente (streaming por polling) -------------------------------


def test_job_chat_flujo_completo(
    cliente: TestClient, vault_poblado: VaultManager
) -> None:
    cliente.app.state.home_chat = HomeChat(  # type: ignore[attr-defined]
        vault_poblado, FakeLLMStream(["Hola ", "mundo"])
    )
    inicio = cliente.post("/api/ai/chat/job", json={"mensaje": "hola"})
    assert inicio.status_code == 200
    assert inicio.json()["estado"] == "generando"

    job_id = inicio.json()["job_id"]
    estado = inicio.json()
    for _ in range(60):
        if estado["estado"] != "generando":
            break
        time.sleep(0.05)
        estado = cliente.get(f"/api/ai/chat/job/{job_id}").json()

    assert estado["estado"] == "fin"
    assert estado["texto"] == "Hola mundo"
    assert estado["meta"]["items"] >= 1


def test_job_chat_error_del_modelo(
    cliente: TestClient, vault_poblado: VaultManager
) -> None:
    class FakeLLMRoto:
        async def completar(
            self,
            prompt: str,
            imagen: bytes | None = None,
            mime_type: str | None = None,
        ) -> str:
            raise RuntimeError("modelo caído")

    cliente.app.state.home_chat = HomeChat(  # type: ignore[attr-defined]
        vault_poblado, FakeLLMRoto()
    )
    job_id = cliente.post(
        "/api/ai/chat/job", json={"mensaje": "hola"}
    ).json()["job_id"]

    estado = {}
    for _ in range(60):
        estado = cliente.get(f"/api/ai/chat/job/{job_id}").json()
        if estado["estado"] != "generando":
            break
        time.sleep(0.05)

    assert estado["estado"] == "error"
    assert "modelo caído" in (estado["detalle"] or "")


def test_job_chat_404_si_no_existe(cliente: TestClient) -> None:
    assert cliente.get("/api/ai/chat/job/no-existe").status_code == 404


def test_job_chat_503_sin_asistente(cliente: TestClient) -> None:
    cliente.app.state.home_chat = None  # type: ignore[attr-defined]
    respuesta = cliente.post("/api/ai/chat/job", json={"mensaje": "hola"})
    assert respuesta.status_code == 503
