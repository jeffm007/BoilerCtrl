"""
NAS Web Dashboard Main Application
Runs on Synology NAS - serves UI and relays commands to Pi
"""

import asyncio
import logging
import sys
import json
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import websockets
import uvicorn
import httpx

# Import shared schemas
from shared.schemas import (
    ZoneStatusModel, ZoneCommandRequest, ZoneUpdateRequest,
    UniformSetpointRequest, ZoneScheduleUpdateRequest,
    ZoneScheduleCloneRequest, GlobalScheduleUpdateRequest
)
from shared.sync_protocol import SyncClient
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - read from environment variables
PI_WS_URL = os.getenv("PI_WS_URL", "ws://localhost:8001/ws")
PI_HTTP_URL = os.getenv("PI_HTTP_URL", "http://localhost:8001")
CACHE_TTL = 30  # seconds - increased since Pi sends updates every 5 seconds
CACHE_SERVE_STALE_TTL = 300  # seconds - serve stale data up to 5 minutes if disconnected
APP_START_TIME = int(datetime.utcnow().timestamp())  # For cache busting

# Global state
sync_client = SyncClient(command_timeout=10.0)  # 10 second timeout for commands
zone_cache = {}  # In-memory cache for zone states
cache_timestamp = None
ws_connection: Optional[websockets.WebSocketClientProtocol] = None
reconnect_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    global reconnect_task

    logger.info("🌐 Starting NAS Web Dashboard...")

    # Register state update handler
    sync_client.register_state_handler(handle_state_update)

    # Start WebSocket connection task
    reconnect_task = asyncio.create_task(maintain_pi_connection())

    logger.info("✅ NAS Web Dashboard started")

    yield

    # Shutdown
    logger.info("🛑 Shutting down NAS Web Dashboard...")
    if reconnect_task:
        reconnect_task.cancel()
    if ws_connection:
        await ws_connection.close()


app = FastAPI(title="Boiler Web Dashboard", version="0.1.0", lifespan=lifespan)

# Mount static files and templates
# Check if running in Docker (frontend at /app/frontend) or locally (../frontend)
if Path("/app/frontend").exists():
    frontend_path = Path("/app/frontend")
else:
    frontend_path = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=frontend_path / "static"), name="static")
templates = Jinja2Templates(directory=frontend_path / "templates")


# State update handler

async def handle_state_update(payload: dict):
    """Handle state update from Pi."""
    global zone_cache, cache_timestamp

    logger.info(f"Received state update: {list(payload.keys())}")
    zones = payload.get("zones", [])
    logger.info(f"Processing {len(zones)} zones")
    updates_made = 0
    updates_skipped = 0

    for zone in zones:
        zone_name = zone.get("ZoneName") or zone.get("zone_name")
        if zone_name:
            # Only update if incoming data is newer than cached data
            incoming_updated_at = zone.get("UpdatedAt")
            cached_zone = zone_cache.get(zone_name)

            if cached_zone:
                cached_updated_at = cached_zone.get("UpdatedAt")
                # Compare timestamps - only update if incoming is newer or equal
                if incoming_updated_at and cached_updated_at:
                    if incoming_updated_at >= cached_updated_at:
                        zone_cache[zone_name] = zone
                        updates_made += 1
                    else:
                        logger.info(f"⏭️  Skipped stale update for {zone_name} (incoming: {incoming_updated_at} < cached: {cached_updated_at})")
                        updates_skipped += 1
                else:
                    # If no timestamp, update anyway
                    zone_cache[zone_name] = zone
                    updates_made += 1
            else:
                # No cached data, accept new zone
                zone_cache[zone_name] = zone
                updates_made += 1

    cache_timestamp = datetime.utcnow()
    logger.info(f"Cache updated: {updates_made} zones updated, {updates_skipped} skipped as stale")


# WebSocket connection management

async def maintain_pi_connection():
    """Maintain WebSocket connection to Pi with auto-reconnect."""
    global ws_connection

    while True:
        try:
            logger.info(f"Connecting to Pi at {PI_WS_URL}...")

            async with websockets.connect(PI_WS_URL) as websocket:
                ws_connection = websocket
                sync_client.reset_reconnect_backoff()
                logger.info("✅ Connected to Pi")

                # Listen for messages
                async for message in websocket:
                    try:
                        logger.debug(f"Received message: {message[:100]}...")
                        data = sync_client.deserialize_message(message)
                        event_type = data["event_type"]
                        logger.info(f"Processing message type: {event_type}")

                        if event_type == "zone_state_update":
                            await sync_client.handle_state_update(data)
                        elif event_type == "command_response":
                            await sync_client.handle_command_response(data)
                        elif event_type == "full_sync_response":
                            logger.info(f"Full sync received with {len(data.get('payload', {}).get('zones', []))} zones")
                            await sync_client.handle_state_update(data)
                        elif event_type == "heartbeat":
                            logger.debug("Heartbeat received")

                    except Exception as e:
                        logger.exception(f"Message handling error: {e}")

        except websockets.exceptions.WebSocketException as e:
            logger.error(f"WebSocket error: {e}")
        except Exception as e:
            logger.exception(f"Connection error: {e}")
        finally:
            ws_connection = None
            sync_client.increase_reconnect_backoff()
            logger.warning(f"Reconnecting in {sync_client.reconnect_backoff}s...")
            await asyncio.sleep(sync_client.reconnect_backoff)


# Helper to send commands to Pi

async def send_command_to_pi(command_type: str, command_data: dict, zone_name: Optional[str] = None):
    """Send command to Pi via WebSocket."""
    if not ws_connection:
        raise HTTPException(status_code=503, detail="Pi controller not connected")

    try:
        response = await sync_client.send_command(
            command_type=command_type,
            command_data=command_data,
            zone_name=zone_name,
            send_func=ws_connection.send
        )

        if not response["success"]:
            raise HTTPException(status_code=500, detail=response.get("error", "Command failed"))

        return response["result"]

    except TimeoutError:
        raise HTTPException(status_code=504, detail="Command timeout - Pi not responding")
    except Exception as e:
        logger.exception(f"Command error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Cache helpers

def is_cache_fresh() -> bool:
    """Check if cache is within TTL."""
    if not cache_timestamp:
        return False
    age = (datetime.utcnow() - cache_timestamp).total_seconds()
    return age < CACHE_TTL


def get_cached_zones():
    """Get zones from cache. Serves stale data if available and not too old."""
    if not cache_timestamp:
        logger.warning("Cache empty - no data received yet")
        return []

    age = (datetime.utcnow() - cache_timestamp).total_seconds()

    if age < CACHE_TTL:
        # Cache is fresh
        return list(zone_cache.values())
    elif age < CACHE_SERVE_STALE_TTL:
        # Cache is stale but not too old - serve it anyway
        logger.debug(f"Serving stale cache (age: {age:.1f}s)")
        return list(zone_cache.values())
    else:
        # Cache is too old
        logger.warning(f"Cache too old ({age:.1f}s) - discarding")
        return []
    return list(zone_cache.values())


# Helper to convert zone from aliased names to snake_case for templates

def normalize_zone_dict(zone: dict) -> dict:
    """Convert zone dict from aliased field names to snake_case."""
    return {
        "zone_name": zone.get("ZoneName") or zone.get("zone_name"),
        "room_name": zone.get("RoomName") or zone.get("room_name"),
        "current_state": zone.get("CurrentState") or zone.get("current_state"),
        "zone_room_temp_f": zone.get("ZoneRoomTemp_F") or zone.get("zone_room_temp_f"),
        "pipe_temp_f": zone.get("PipeTemp_F") or zone.get("pipe_temp_f"),
        "target_setpoint_f": zone.get("TargetSetpoint_F") or zone.get("target_setpoint_f"),
        "control_mode": zone.get("ControlMode") or zone.get("control_mode"),
        "updated_at": zone.get("UpdatedAt") or zone.get("updated_at"),
        "updated_date": zone.get("UpdatedDate") or zone.get("updated_date"),
        "updated_time": zone.get("UpdatedTime") or zone.get("updated_time"),
    }


# Web UI routes

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    # Get zones from cache or Pi
    zones = get_cached_zones()
    zones = [normalize_zone_dict(z) for z in zones]

    # Create zone choices (excluding Boiler)
    selectable_zones = [z["zone_name"] for z in zones if z["zone_name"] != "Boiler"]

    # Get system status (boiler zone)
    system_status = next((z for z in zones if z["zone_name"] == "Boiler"), None)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "zones": zones,
        "system": system_status,
        "zone_choices": selectable_zones,
        "cache_version": APP_START_TIME,
    })


@app.get("/graphs", response_class=HTMLResponse)
async def graphs_page(request: Request):
    """Graphs page."""
    zones = [normalize_zone_dict(z) for z in get_cached_zones()]
    selectable_zones = [z["zone_name"] for z in zones if z["zone_name"] != "Boiler"]

    return templates.TemplateResponse("graphs.html", {
        "request": request,
        "active_page": "graphs",
        "zones": zones,  # Pass zones for rendering cards
        "zone_choices": selectable_zones,
        "cache_version": APP_START_TIME,
    })


@app.get("/scheduler", response_class=HTMLResponse)
async def scheduler_page(request: Request):
    """Scheduler page."""
    zones = [normalize_zone_dict(z) for z in get_cached_zones()]
    zone_choices = [
        {"zone": z["zone_name"], "room": z["room_name"]}
        for z in zones if z["zone_name"] != "Boiler"
    ]

    return templates.TemplateResponse("scheduler.html", {
        "request": request,
        "active_page": "scheduler",
        "zone_choices": zone_choices,
        "cache_version": APP_START_TIME,
    })


@app.get("/metrics", response_class=HTMLResponse)
async def metrics_page(request: Request):
    """Metrics page."""
    zones = [normalize_zone_dict(z) for z in get_cached_zones()]
    zone_choices = [
        {"zone": z["zone_name"], "room": z["room_name"]}
        for z in zones if z["zone_name"] != "Boiler"
    ]

    return templates.TemplateResponse("metrics.html", {
        "request": request,
        "active_page": "metrics",
        "zone_choices": zone_choices,
        "cache_version": APP_START_TIME,
    })


# API routes

@app.get("/api/zones")
def list_zones():
    """Get all zone states from cache."""
    zones = get_cached_zones()
    if not zones:
        raise HTTPException(status_code=503, detail="No data available - Pi may be disconnected")
    return zones


@app.get("/api/zones/stats")
async def get_zone_stats(
    window: str = Query("day", pattern="^(day|week|month)$"),
    day: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
):
    """Proxy zone statistics request to Pi controller."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {"window": window}
            if day:
                params["day"] = day
            response = await client.get(
                f"{PI_HTTP_URL}/api/zones/stats",
                params=params
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to proxy zone stats to Pi: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to fetch zone stats from Pi: {str(e)}")


@app.get("/api/events")
async def list_events(
    source: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = Query(200, ge=1, le=2000)
):
    """Proxy events list request to Pi controller."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {"limit": limit}
            if source:
                params["source"] = source
            if since:
                params["since"] = since
            if until:
                params["until"] = until
            response = await client.get(
                f"{PI_HTTP_URL}/api/events",
                params=params
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to proxy events to Pi: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to fetch events from Pi: {str(e)}")


@app.get("/api/zones/{zone_name}")
def get_zone(zone_name: str):
    """Get specific zone state from cache."""
    zone = zone_cache.get(zone_name)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone {zone_name} not found")
    return zone


@app.post("/api/zones/{zone_name}/command")
async def zone_command(zone_name: str, payload: ZoneCommandRequest):
    """Send command to zone via Pi."""
    result = await send_command_to_pi(
        command_type="zone_command",
        command_data=payload.model_dump(),
        zone_name=zone_name
    )
    return result


@app.put("/api/zones/{zone_name}")
@app.patch("/api/zones/{zone_name}")
async def update_zone(zone_name: str, payload: ZoneUpdateRequest):
    """Update zone setpoint/mode via Pi."""
    result = await send_command_to_pi(
        command_type="zone_update",
        command_data=payload.model_dump(),
        zone_name=zone_name
    )
    return result


@app.post("/api/zones/setpoint/uniform")
async def uniform_setpoint(payload: UniformSetpointRequest):
    """Set uniform setpoint for all zones via Pi."""
    result = await send_command_to_pi(
        command_type="uniform_setpoint",
        command_data=payload.model_dump()
    )
    return result


@app.get("/api/system")
def system_status():
    """Get system status (placeholder - not cached yet)."""
    return {
        "OutsideTemp_F": None,
        "UpdatedAt": datetime.utcnow().isoformat() + "Z"
    }


@app.get("/api/connection/status")
def connection_status():
    """Get Pi connection status."""
    return {
        "connected": ws_connection is not None,
        "cache_fresh": is_cache_fresh(),
        "cached_zones": len(zone_cache),
        "last_update": cache_timestamp.isoformat() + "Z" if cache_timestamp else None,
        "reconnect_backoff": sync_client.reconnect_backoff
    }


@app.get("/health")
def health():
    """Health check endpoint."""
    return {
        "status": "healthy" if ws_connection else "degraded",
        "pi_connected": ws_connection is not None,
        "cache_size": len(zone_cache),
        "cache_fresh": is_cache_fresh()
    }


# Stub routes for functionality not yet implemented
# These would normally query the Pi or local replica

@app.get("/api/zones/{zone_name}/statistics")
def zone_statistics(zone_name: str):
    """Zone statistics (not implemented in distributed mode)."""
    raise HTTPException(status_code=501, detail="Statistics not yet available in distributed mode")


@app.post("/api/zones/history/batch")
async def zone_history_batch(
    request: Request,
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(2000, ge=10, le=12000),
    day: Optional[str] = Query(None),
    tz: str = Query("America/Denver"),
    span_days: int = Query(1, ge=1, le=31),
    max_samples: int = Query(4000, ge=200, le=20000),
):
    """Proxy batch history requests to Pi controller."""
    try:
        # Get request body (zone list)
        body = await request.json()

        # Build query parameters
        params = {
            "hours": hours,
            "limit": limit,
            "tz": tz,
            "span_days": span_days,
            "max_samples": max_samples,
        }
        if day:
            params["day"] = day

        # Forward request to Pi
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{PI_HTTP_URL}/api/zones/history/batch",
                json=body,
                params=params
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to proxy history request to Pi: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch history from Pi controller: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error in history proxy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/zones/{zone_name}/history")
async def zone_history(
    zone_name: str,
    limit: int = Query(4000, ge=1, le=10000),
    tz: str = Query("UTC"),
    day: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    max_samples: int = Query(800, ge=100, le=2000)
):
    """Proxy zone history request to Pi controller."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            params = {
                "limit": limit,
                "tz": tz,
                "max_samples": max_samples
            }
            if day:
                params["day"] = day
            response = await client.get(
                f"{PI_HTTP_URL}/api/zones/{zone_name}/history",
                params=params
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to proxy history request to Pi: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to fetch history from Pi: {str(e)}")


@app.get("/api/zones/{zone_name}/schedule")
async def get_zone_schedule(zone_name: str):
    """Proxy zone schedule request to Pi controller."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{PI_HTTP_URL}/api/zones/{zone_name}/schedule")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to proxy schedule request to Pi: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to fetch schedule from Pi: {str(e)}")


@app.put("/api/zones/{zone_name}/schedule")
async def update_zone_schedule(zone_name: str, request: Request):
    """Proxy zone schedule update to Pi controller."""
    try:
        payload = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.put(
                f"{PI_HTTP_URL}/api/zones/{zone_name}/schedule",
                json=payload
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to proxy schedule update to Pi: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to update schedule on Pi: {str(e)}")


@app.post("/api/zones/{zone_name}/schedule/clone")
async def clone_zone_schedule(zone_name: str, request: Request):
    """Proxy zone schedule clone to Pi controller."""
    try:
        payload = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{PI_HTTP_URL}/api/zones/{zone_name}/schedule/clone",
                json=payload
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to proxy schedule clone to Pi: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to clone schedule on Pi: {str(e)}")


@app.get("/api/schedule/default")
async def get_default_schedule():
    """Proxy default schedule request to Pi controller."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{PI_HTTP_URL}/api/schedule/default")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to proxy default schedule request to Pi: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to fetch default schedule from Pi: {str(e)}")


@app.get("/api/schedule/presets")
async def list_presets():
    """Proxy presets list request to Pi controller."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{PI_HTTP_URL}/api/schedule/presets")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to proxy presets list to Pi: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to fetch presets from Pi: {str(e)}")


@app.post("/api/schedule/presets")
async def create_preset(request: Request):
    """Proxy preset creation to Pi controller."""
    try:
        payload = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{PI_HTTP_URL}/api/schedule/presets",
                json=payload
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to proxy preset creation to Pi: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to create preset on Pi: {str(e)}")


@app.get("/api/schedule/presets/{preset_id}")
async def get_preset(preset_id: int):
    """Proxy preset get request to Pi controller."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{PI_HTTP_URL}/api/schedule/presets/{preset_id}")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to proxy preset get to Pi: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to fetch preset from Pi: {str(e)}")


@app.put("/api/schedule/presets/{preset_id}")
async def update_preset(preset_id: int, request: Request):
    """Proxy preset update to Pi controller."""
    try:
        payload = await request.json()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.put(
                f"{PI_HTTP_URL}/api/schedule/presets/{preset_id}",
                json=payload
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to proxy preset update to Pi: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to update preset on Pi: {str(e)}")


@app.delete("/api/schedule/presets/{preset_id}")
async def delete_preset(preset_id: int):
    """Proxy preset deletion to Pi controller."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(f"{PI_HTTP_URL}/api/schedule/presets/{preset_id}")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Failed to proxy preset deletion to Pi: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to delete preset on Pi: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
