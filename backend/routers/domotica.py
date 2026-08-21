"""Router de domótica (Fase 4a): webhook de botones físicos.

POST /api/domotica/webhook/boton: mapea botones físicos del hogar a acciones
del vault. El mapeo se carga, por este orden:
1. De un dict inyectado en ``app.state.botones_config`` (para tests o
   configuración en caliente).
2. Del archivo ``config/botones.json`` del vault (fuente de verdad).

Formato de config/botones.json::

    {
      "boton_cocina": {
        "descripcion": "Botón junto a la nevera",
        "acciones": {
          "simple": {"tipo": "consumir_item", "item_id": "item_leche",
                     "cantidad": 1.0},
          "doble": {"tipo": "completar_tarea", "task_id": "tarea_basura"}
        }
      }
    }

Acciones soportadas:
- ``consumir_item``: descuenta ``cantidad`` (por defecto 1.0) de un ítem
  vía VaultManager.consume_item (motor FIFO + trigger de lista de compra).
- ``completar_tarea``: completa una tarea vía GoogleSync.complete_task
  (historial, rotación de convivientes, reprogramación y sync remoto).

El integrador debe registrar este router en main.py:
    from backend.routers.domotica import router as domotica_router
    app.include_router(domotica_router)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.models import ResultadoConsumo, Tarea
from backend.vault_manager import VaultManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/domotica", tags=["domotica"])


class PeticionBoton(BaseModel):
    """Cuerpo de POST /api/domotica/webhook/boton."""

    boton_id: str
    accion: str = Field(default="simple")


class RespuestaBoton(BaseModel):
    """Resultado de ejecutar la acción de un botón físico."""

    boton_id: str
    accion: str
    tipo: str
    resultado_consumo: Optional[ResultadoConsumo] = None
    tarea_completada: Optional[Tarea] = None


def _vault(request: Request) -> VaultManager:
    """Recupera el VaultManager del estado de la app."""
    return request.app.state.vault


def _cargar_botones(request: Request) -> dict[str, Any]:
    """Carga el mapa de botones: dict inyectado o config/botones.json."""
    inyectado: Optional[dict[str, Any]] = getattr(
        request.app.state, "botones_config", None
    )
    if inyectado is not None:
        return inyectado
    ruta = _vault(request).vault_path / "config" / "botones.json"
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("config/botones.json corrupto: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="config/botones.json del vault no es JSON válido",
        ) from exc


async def _ejecutar_accion(
    request: Request,
    boton_id: str,
    nombre_accion: str,
    accion: dict[str, Any],
) -> RespuestaBoton:
    """Ejecuta la acción mapeada y devuelve el resultado estructurado."""
    tipo = accion.get("tipo")
    if tipo == "consumir_item":
        item_id = accion.get("item_id")
        if not item_id:
            raise HTTPException(
                status_code=400,
                detail=f"Acción consumir_item sin item_id ({boton_id})",
            )
        cantidad = float(accion.get("cantidad", 1.0))
        try:
            resultado = await _vault(request).consume_item(item_id, cantidad)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return RespuestaBoton(
            boton_id=boton_id,
            accion=nombre_accion,
            tipo=tipo,
            resultado_consumo=resultado,
        )
    if tipo == "completar_tarea":
        task_id = accion.get("task_id")
        if not task_id:
            raise HTTPException(
                status_code=400,
                detail=f"Acción completar_tarea sin task_id ({boton_id})",
            )
        sync = getattr(request.app.state, "google_sync", None)
        if sync is None:
            raise HTTPException(
                status_code=503,
                detail="GoogleSync no configurado en la app",
            )
        try:
            tarea = await sync.complete_task(task_id, completed_by=boton_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return RespuestaBoton(
            boton_id=boton_id,
            accion=nombre_accion,
            tipo=tipo,
            tarea_completada=tarea,
        )
    raise HTTPException(
        status_code=400,
        detail=f"Tipo de acción desconocido: {tipo!r} ({boton_id})",
    )


@router.post("/webhook/boton", response_model=RespuestaBoton)
async def webhook_boton(
    request: Request, peticion: PeticionBoton
) -> RespuestaBoton:
    """Webhook para botones físicos (p. ej. desde Home Assistant/ESPHome)."""
    botones = _cargar_botones(request)
    boton = botones.get(peticion.boton_id)
    if boton is None:
        raise HTTPException(
            status_code=404,
            detail=f"Botón no configurado: {peticion.boton_id}",
        )
    accion = boton.get("acciones", {}).get(peticion.accion)
    if accion is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Acción {peticion.accion!r} no configurada para "
                f"el botón {peticion.boton_id}"
            ),
        )
    logger.info(
        "Botón %s pulsado (%s): %s", peticion.boton_id, peticion.accion, accion
    )
    return await _ejecutar_accion(
        request, peticion.boton_id, peticion.accion, accion
    )
