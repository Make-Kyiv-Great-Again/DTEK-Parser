import logging
import asyncio
from typing import List, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import httpx
from collections import Counter
from pydantic import BaseModel, Field

from app.yasno.service import yasno_service
from app.outages.service import outage_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2")

async def fetch_overpass_data(query: str) -> dict:
    """Queries OSM Overpass API servers with retry fallbacks."""
    instances = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.osm.ch/api/interpreter"
    ]
    for url in instances:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(url, params={"data": query})
                if r.status_code == 200:
                    return r.json()
        except Exception as e:
            logger.warning(f"Overpass instance {url} failed: {e}")
    raise Exception("All Overpass API instances failed.")

def partition_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float, rows: int = 6, cols: int = 6) -> List[Dict[str, Any]]:
    """Divides a bounding box into N x M rectangular grid cells."""
    lat_step = (max_lat - min_lat) / rows
    lon_step = (max_lon - min_lon) / cols
    cells = []
    for r in range(rows):
        for c in range(cols):
            cells.append({
                "zone_id": f"cell_{r}_{c}",
                "min_lat": min_lat + r * lat_step,
                "max_lat": min_lat + (r + 1) * lat_step,
                "min_lon": min_lon + c * lon_step,
                "max_lon": min_lon + (c + 1) * lon_step,
            })
    return cells

async def stream_grid_updates(websocket: WebSocket, bbox: dict):
    """Processes Overpass elements, partitions BBox, resolves cell statuses, and streams results."""
    try:
        min_lat = bbox["min_lat"]
        min_lon = bbox["min_lon"]
        max_lat = bbox["max_lat"]
        max_lon = bbox["max_lon"]

        await websocket.send_json({"type": "status", "message": "Querying Overpass API for geometries..."})
        
        # Query OSM Overpass for building tags in the viewport
        query = f'[out:json];way({min_lat},{min_lon},{max_lat},{max_lon})["addr:housenumber"]["addr:street"];out center;'
        data = await fetch_overpass_data(query)
        elements = data.get("elements", [])

        if not elements:
            await websocket.send_json({"type": "status", "message": "No buildings found in this viewport area."})
            return

        await websocket.send_json({"type": "status", "message": f"Found {len(elements)} buildings. Subdividing grid..."})

        # Divide viewport into a 6x6 grid
        cells = partition_bbox(min_lat, min_lon, max_lat, max_lon, rows=6, cols=6)
        
        # Assign buildings to cells
        cell_buildings = {c["zone_id"]: [] for c in cells}
        for el in elements:
            center = el.get("center")
            if not center:
                continue
            lat = center["lat"]
            lon = center["lon"]
            street = el.get("tags", {}).get("addr:street")
            house = el.get("tags", {}).get("addr:housenumber")
            if not street or not house:
                continue

            for cell in cells:
                if cell["min_lat"] <= lat <= cell["max_lat"] and cell["min_lon"] <= lon <= cell["max_lon"]:
                    cell_buildings[cell["zone_id"]].append((street, house))
                    break

        await websocket.send_json({"type": "status", "message": "Resolving grid outages progressive stream..."})

        # Process and stream grid cells sequentially
        for cell in cells:
            buildings = cell_buildings[cell["zone_id"]]
            if not buildings:
                continue  # Skip empty cells

            # Take at most 3 buildings per cell to evaluate cell-wide status
            sample = buildings[:3]
            statuses = []
            reasons = []

            for street, house in sample:
                try:
                    region_id = 25  # Default Kyiv
                    dso_id = 902
                    
                    street_id, resolved_street = await yasno_service.resolve_street_id(
                        region_id, street, dso_id, allow_split_fallback=True
                    )
                    house_id, resolved_house = await yasno_service.resolve_house_id(
                        region_id, street_id, house, dso_id
                    )
                    res = await outage_service.get_status(
                        region_id, street_id, house_id, dso_id, resolved_street, resolved_house
                    )
                    statuses.append(res["power_status"])
                    reasons.append(res["status_reason"])
                except Exception:
                    pass

            if not statuses:
                continue

            # Determine majority status for the cell
            counter = Counter(statuses)
            majority_status = counter.most_common(1)[0][0]
            majority_reason = next(r for r, s in zip(reasons, statuses) if s == majority_status)

            # Send update for this specific cell
            await websocket.send_json({
                "type": "zone_update",
                "zone_id": cell["zone_id"],
                "bbox": {
                    "min_lat": cell["min_lat"],
                    "min_lon": cell["min_lon"],
                    "max_lat": cell["max_lat"],
                    "max_lon": cell["max_lon"]
                },
                "status": majority_status,
                "reason": majority_reason
            })
            # Small async sleep to smooth rendering stream
            await asyncio.sleep(0.02)

        await websocket.send_json({"type": "status", "message": "Grid scan completed."})

    except asyncio.CancelledError:
        logger.info("Grid streaming task cancelled due to viewport change.")
        raise
    except Exception as e:
        logger.error(f"Error in grid stream process: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass

@router.websocket("/ws/outages")
async def websocket_outages_endpoint(websocket: WebSocket):
    """WebSocket endpoint to subscribe to viewport bounding box updates and receive streamed grid status updates."""
    await websocket.accept()
    logger.info("WebSocket connection established for outages v2.")
    
    active_task = None
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("action") == "subscribe_viewport":
                bbox = data.get("bbox")
                if not bbox:
                    await websocket.send_json({"type": "error", "message": "Missing 'bbox' fields."})
                    continue
                
                # Cancel previous streaming task if running
                if active_task and not active_task.done():
                    active_task.cancel()
                    try:
                        await active_task
                    except asyncio.CancelledError:
                        pass
                
                # Spawn a new task to stream this viewport's grid cells
                active_task = asyncio.create_task(stream_grid_updates(websocket, bbox))
                
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
    subscription_action: str = Field("subscribe_viewport", description="Action string to trigger grid subscriptions")
    subscription_payload: dict = Field(..., description="Required subscription payload parameters (bbox coordinates)")
    stream_response_payload: dict = Field(..., description="Details of progressively streamed grid cell status responses")

@router.get("/ws/info", response_model=WebSocketInfoResponse)
async def get_websocket_info():
    """Retrieve metadata and description for the real-time WebSocket outages endpoint."""
    return {
        "websocket_url": "/api/v2/ws/outages",
        "protocol": "JSON",
        "subscription_action": "subscribe_viewport",
        "subscription_payload": {
            "action": "subscribe_viewport",
            "bbox": {
                "min_lat": "float (e.g. 50.4400)",
                "min_lon": "float (e.g. 30.5000)",
                "max_lat": "float (e.g. 50.4600)",
                "max_lon": "float (e.g. 30.5300)"
            }
        },
        "stream_response_payload": {
            "type": "zone_update",
            "zone_id": "string (e.g. cell_0_0)",
            "bbox": {
                "min_lat": "float",
                "min_lon": "float",
                "max_lat": "float",
                "max_lon": "float"
            },
            "status": "string (ON | OFF | PROBABLE | EMERGENCY)",
            "reason": "string (detailed description of current outage reason)"
        }
    }
