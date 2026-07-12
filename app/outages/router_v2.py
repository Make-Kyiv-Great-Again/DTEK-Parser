import logging
import asyncio
from typing import List, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.yasno.service import yasno_service
from app.outages.service import outage_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2")

async def resolve_statuses_progressively(websocket: WebSocket, addresses: List[Dict[str, str]]):
    """Resolves outages for a list of street/house addresses and streams them back one-by-one."""
    region_id = 25  # Kyiv
    dso_id = 902
    
    for item in addresses:
        street = item.get("street")
        house = item.get("house")
        if not street or not house:
            continue
            
        try:
            street_id, resolved_street = await yasno_service.resolve_street_id(
                region_id, street, dso_id, allow_split_fallback=True
            )
            house_id, resolved_house = await yasno_service.resolve_house_id(
                region_id, street_id, house, dso_id
            )
            res = await outage_service.get_status(
                region_id, street_id, house_id, dso_id, resolved_street, resolved_house
            )
            
            await websocket.send_json({
                "type": "status_update",
                "street": street,
                "house": house,
                "status": res["power_status"],
                "reason": res["status_reason"]
            })
        except Exception as e:
            # Send fallback unknown status so the client doesn't hang
            await websocket.send_json({
                "type": "status_update",
                "street": street,
                "house": house,
                "status": "UNKNOWN",
                "reason": str(e)
            })
        # Small sleep to smooth event loop and socket throughput
        await asyncio.sleep(0.01)

@router.websocket("/ws/outages")
async def websocket_outages_endpoint(websocket: WebSocket):
    """WebSocket endpoint to progressively resolve building statuses."""
    await websocket.accept()
    logger.info("WebSocket connection established for outages v2.")
    
    active_task = None
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("action") == "resolve_statuses":
                addresses = data.get("addresses")
                if not addresses:
                    await websocket.send_json({"type": "error", "message": "Missing 'addresses' list."})
                    continue
                
                # Cancel previous streaming task if running
                if active_task and not active_task.done():
                    active_task.cancel()
                    try:
                        await active_task
                    except asyncio.CancelledError:
                        pass
                
                # Spawn new progressive resolution task
                active_task = asyncio.create_task(resolve_statuses_progressively(websocket, addresses))
                
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
    finally:
        if active_task and not active_task.done():
            active_task.cancel()
            try:
                await active_task
            except asyncio.CancelledError:
                pass
        try:
            await websocket.close()
        except:
            pass

class WebSocketInfoResponse(BaseModel):
    websocket_url: str = Field(..., description="WebSocket URL path for real-time viewport status updates")
    protocol: str = Field("JSON", description="Message serialization protocol")
    subscription_action: str = Field("resolve_statuses", description="Action string to trigger address resolutions")
    subscription_payload: dict = Field(..., description="Required subscription payload parameters (address list)")
    stream_response_payload: dict = Field(..., description="Details of progressively streamed address status responses")

@router.get("/ws/info", response_model=WebSocketInfoResponse)
async def get_websocket_info():
    """Retrieve metadata and description for the real-time WebSocket outages endpoint."""
    return {
        "websocket_url": "/api/v2/ws/outages",
        "protocol": "JSON",
        "subscription_action": "resolve_statuses",
        "subscription_payload": {
            "action": "resolve_statuses",
            "addresses": [
                {"street": "вулиця Івана Франка", "house": "28"}
            ]
        },
        "stream_response_payload": {
            "type": "status_update",
            "street": "string",
            "house": "string",
            "status": "string (ON | OFF | UNKNOWN)",
            "reason": "string"
        }
    }
