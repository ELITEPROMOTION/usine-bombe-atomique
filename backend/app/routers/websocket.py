"""WebSocket endpoint pour progression temps reel (stub)."""
import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/tasks/{task_id}")
async def task_stream(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    try:
        await websocket.send_json({"type": "connected", "task_id": task_id})
        # Boucle keep-alive basique. L'orchestrateur publiera les events via Redis pub/sub en V1.1.
        while True:
            await asyncio.sleep(15)
            await websocket.send_json({"type": "ping", "task_id": task_id})
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "error": str(exc)})
        finally:
            await websocket.close()
