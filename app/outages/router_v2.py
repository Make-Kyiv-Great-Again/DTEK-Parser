import logging
import asyncio
import re
import urllib.parse
import subprocess
import json
from typing import List, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import httpx
from pydantic import BaseModel, Field

from app.yasno.service import yasno_service
from app.outages.service import outage_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2")

def parse_house_num(house_str: str) -> int:
    """Extracts the first number sequence from a house number string."""
    match = re.search(r'\d+', house_str)
    return int(match.group(0)) if match else 0

async def fetch_overpass_data(query: str) -> dict:
    """Queries OSM Overpass API servers with manual url-encoding, Accept-Encoding restrictions, and curl fallback."""
    instances = [
        "https://svitlo-finder.xyz/overpass/api/interpreter"
    ]
    query_encoded = urllib.parse.quote(query)
    
    headers = {
        "User-Agent": "curl/8.7.1",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate"  # Explicitly omit 'br' (Brotli) to prevent 406 Not Acceptable
    }
    
    # 1. Try standard async HTTP requests
    for base_url in instances:
        url = f"{base_url}?data={query_encoded}"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    return r.json()
                logger.warning(f"Overpass instance {url} returned status code {r.status_code}")
        except Exception as e:
            logger.warning(f"Overpass instance {url} failed: {e}")
            
    # 2. Final bulletproof fallback: execute curl as a subprocess (bypasses library level blocks)
    logger.info("Falling back to local curl execution for Overpass query...")
    try:
        cmd = [
            "curl",
            "-s",
            "-G",
            "https://svitlo-finder.xyz/overpass/api/interpreter",
            "--data-urlencode",
            f"data={query}"
        ]
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=25.0)
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        else:
            logger.warning(f"Process fallback curl failed: {result.stderr or result.stdout[:200]}")
    except Exception as e:
        logger.warning(f"Failed executing process fallback curl: {e}")
        
    raise Exception("All Overpass API instances and process fallbacks failed or timed out.")

async def resolve_and_stream_buildings(websocket: WebSocket, bbox: dict):
    """Fetches buildings in viewport, resolves outage statuses using extrapolation, and streams in batches."""
    try:
        min_lat = bbox["min_lat"]
        min_lon = bbox["min_lon"]
        max_lat = bbox["max_lat"]
        max_lon = bbox["max_lon"]

        await websocket.send_json({"type": "status", "message": "Шукаємо будівлі у полі зору..."})
        
        # Query OSM Overpass for building tags and full geometries (just like demo v1)
        query = f'[out:json];way({min_lat},{min_lon},{max_lat},{max_lon})["addr:housenumber"]["addr:street"];out geom;'
        logger.info(f"Constructing Overpass geom query: {query}")
        data = await fetch_overpass_data(query)
        elements = data.get("elements", [])

        if not elements:
            await websocket.send_json({"type": "status", "message": "У цьому секторі не знайдено будівель."})
            return

        await websocket.send_json({"type": "status", "message": f"Знайдено {len(elements)} будівель. Опитування статусів..."})

        # Group buildings by street
        buildings_by_street = {}
        for el in elements:
            street = el.get("tags", {}).get("addr:street")
            house = el.get("tags", {}).get("addr:housenumber")
            geom = el.get("geometry")
            if not street or not house or not geom:
                continue
            
            if street not in buildings_by_street:
                buildings_by_street[street] = []
            buildings_by_street[street].append(el)

        # For each street, pick up to 3 representative houses and query statuses
        street_resolved_statuses = {}
        region_id = 25  # Kyiv
        dso_id = 902

        for street, street_elements in buildings_by_street.items():
            # Pick representative sample (up to 3 houses)
            sample_elements = street_elements[:3]
            resolved_houses = []
            
            for el in sample_elements:
                house = el["tags"]["addr:housenumber"]
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
                    resolved_houses.append({
                        "house_num": parse_house_num(house),
                        "status": res["power_status"],
                        "reason": res["status_reason"]
                    })
                except Exception:
                    pass
            
            street_resolved_statuses[street] = resolved_houses

        # Extrapolate statuses for all buildings and prepare batch payload
        all_resolved_buildings = []
        for street, street_elements in buildings_by_street.items():
            resolved_list = street_resolved_statuses.get(street, [])
            valid_resolved = [item for item in resolved_list if item["status"] != "UNKNOWN"]
            list_to_use = valid_resolved if valid_resolved else resolved_list

            for el in street_elements:
                house = el["tags"]["addr:housenumber"]
                status = "UNKNOWN"
                reason = "Немає даних по вулиці"
                mapping_type = "unknown"

                if list_to_use:
                    # Find closest representative house by parsed number
                    target_num = parse_house_num(house)
                    closest = min(list_to_use, key=lambda item: abs(item["house_num"] - target_num))
                    status = closest["status"]
                    reason = closest["reason"]
                    # If this house was queried directly
                    if any(item["house_num"] == target_num for item in resolved_list):
                        mapping_type = "direct"
                    else:
                        mapping_type = "propagated"

                all_resolved_buildings.append({
                    "id": el["id"],
                    "street": street,
                    "house": house,
                    "status": status,
                    "reason": reason,
                    "mapping_type": mapping_type,
                    "geometry": [[pt["lat"], pt["lon"]] for pt in el["geometry"]]
                })

        # Stream buildings in batches of 50
        batch_size = 50
        for i in range(0, len(all_resolved_buildings), batch_size):
            batch = all_resolved_buildings[i:i + batch_size]
            await websocket.send_json({
                "type": "buildings_batch",
                "buildings": batch
            })
            # Small non-blocking sleep to allow UI to render progressively
            await asyncio.sleep(0.05)

        await websocket.send_json({"type": "status", "message": "completed"})

    except asyncio.CancelledError:
        logger.info("Outages streaming task cancelled due to viewport change.")
        raise
    except Exception as e:
        logger.error(f"Error in outages stream process: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass

@router.websocket("/ws/outages")
async def websocket_outages_endpoint(websocket: WebSocket):
    """WebSocket endpoint to subscribe to viewport bounding box updates and stream building statuses progressively."""
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
                
                # Spawn a new task to stream resolved buildings
                active_task = asyncio.create_task(resolve_and_stream_buildings(websocket, bbox))
                
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
    subscription_action: str = Field("subscribe_viewport", description="Action string to trigger viewport subscriptions")
    subscription_payload: dict = Field(..., description="Required subscription payload parameters (bbox coordinates)")
    stream_response_payload: dict = Field(..., description="Details of progressively streamed batch building responses")

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
            "type": "buildings_batch",
            "buildings": [
                {
                    "id": "integer",
                    "street": "string",
                    "house": "string",
                    "status": "string (ON | OFF | UNKNOWN)",
                    "reason": "string",
                    "mapping_type": "string (direct | propagated | unknown)",
                    "geometry": "list of lists of floats [[lat, lon], ...]"
                }
            ]
        }
    }
