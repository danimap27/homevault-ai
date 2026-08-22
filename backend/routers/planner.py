"""Router del planificador de cocina (Fase 4c).

Endpoints:
- GET  /api/planner/rescue         -> rescue_chef
- POST /api/planner/batch-cooking  -> batch_cooking
- POST /api/planner/evento         -> modo_evento
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.planner import (
    InsufficientStockError,
    Planner,
    ResultadoAsignarPlan,
    ResultadoBatchCooking,
    ResultadoEvento,
    SugerenciaRescate,
)
from backend.vault_manager import VaultManager

router = APIRouter(prefix="/api/planner", tags=["planner"])


class PeticionBatchCooking(BaseModel):
    """Cuerpo de POST /api/planner/batch-cooking."""

    receta_ids: list[str] = Field(min_length=1)
    destino: str = "congelador"
    dias_max_congelador: Optional[int] = Field(default=None, gt=0)


class PeticionEvento(BaseModel):
    """Cuerpo de POST /api/planner/evento."""

    receta_ids: list[str] = Field(min_length=1)
    invitados: int = Field(gt=0)


def _planner(request: Request) -> Planner:
    """Construye el Planner sobre el VaultManager del estado de la app."""
    vault: VaultManager = request.app.state.vault
    return Planner(vault)


@router.get("/rescue", response_model=list[SugerenciaRescate])
async def rescue_chef(
    request: Request, dias: int = Query(default=4, ge=0)
) -> list[SugerenciaRescate]:
    """Recetas que rescatan los ítems que caducan en <= `dias` días."""
    return await _planner(request).rescue_chef(dias=dias)


@router.post("/batch-cooking", response_model=ResultadoBatchCooking)
async def batch_cooking(
    request: Request, peticion: PeticionBatchCooking
) -> ResultadoBatchCooking:
    """Descuenta crudos del inventario y crea un tupper por receta."""
    try:
        return await _planner(request).batch_cooking(
            peticion.receta_ids,
            destino=peticion.destino,
            dias_max_congelador=peticion.dias_max_congelador,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/evento", response_model=ResultadoEvento)
async def modo_evento(
    request: Request, peticion: PeticionEvento
) -> ResultadoEvento:
    """Escala recetas por invitados y lista solo los faltantes."""
    try:
        return await _planner(request).modo_evento(
            peticion.receta_ids, peticion.invitados
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class PeticionAsignarPlan(BaseModel):
    """Cuerpo de POST /api/planner/assign."""

    semana_iso: str
    dia: str
    toma: str
    receta_id: str
    raciones: int = Field(ge=1)


@router.post("/assign", response_model=ResultadoAsignarPlan)
async def asignar_receta_al_plan(
    request: Request, peticion: PeticionAsignarPlan
) -> ResultadoAsignarPlan:
    """Asigna una receta a un slot del planificador y añade faltantes a compra."""
    try:
        return await _planner(request).assign_recipe_to_plan(
            semana_iso=peticion.semana_iso,
            dia=peticion.dia,
            toma=peticion.toma,
            receta_id=peticion.receta_id,
            raciones=peticion.raciones,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InsufficientStockError as exc:
        # No debería ocurrir porque assign no consume stock, pero se deja
        # controlado por robustez.
        raise HTTPException(
            status_code=409,
            detail={
                "mensaje": "Stock insuficiente para la receta",
                "faltantes": [f.model_dump() for f in exc.faltantes],
            },
        ) from exc
