"""Router WebSocket de HomeVault AI (Fase 4).

Expone /ws, donde los clientes se registran en el WebSocketManager para
recibir los eventos del vault (INVENTORY_UPDATED, TASK_CHANGED, etc.).

Integración pendiente en main.py:
    from backend.routers.ws import router as ws_router
    app.include_router(ws_router)
y en el lifespan: app.state.ws_manager = WebSocketManager()
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.watcher import WebSocketManager

logger = logging.getLogger(__name__)

router = APIRouter()

# Manager de respaldo si el lifespan no inyecta app.state.ws_manager
_fallback_manager = WebSocketManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Registra el cliente en el manager y mantiene la conexión viva.

    Los mensajes entrantes del cliente se ignoran (canal solo de salida);
    la conexión se mantiene hasta que el cliente la cierra.
    """
    manager: WebSocketManager = (
        getattr(websocket.app.state, "ws_manager", None) or _fallback_manager
    )
    await manager.connect(websocket)
    logger.info("Cliente WebSocket conectado (%d activos)", manager.num_conexiones)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(
            "Cliente WebSocket desconectado (%d activos)", manager.num_conexiones
        )
