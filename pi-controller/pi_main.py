"""
Pi Controller Main Application
Runs on Raspberry Pi - manages hardware and publishes state via WebSocket
"""

import asyncio
import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

# Add parent and shared to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
import uvicorn

# Import from backend (will be refactored into pi-controller package)
from backend.database import init_db
from backend.config import settings
from backend import repositories
from backend.services.zone_service import ZoneService
from backend.services.event_service import EventService
from backend.hardware.controller import MockHardwareController

# Log configuration paths for debugging
logger = logging.getLogger(__name__)
logger.info(f"📂 Zone config path: {settings.zone_config_path.absolute()}")
logger.info(f"📂 Database path: {settings.database_path.absolute()}")
logger.info(f"🗺️  Zone room map: {settings.zone_room_map}")

# Import shared schemas and sync
from shared.schemas import (
    ZoneCommandRequest, ZoneUpdateRequest, ZoneEventPayload,
    BoilerEventPayload, UniformSetpointRequest, ZoneHistoryBatchRequest,
    SchedulePresetSummaryModel, SchedulePresetDetailModel,
    SchedulePresetCreateRequest, SchedulePresetUpdateRequest,
    ZoneStatisticsModel, EventLogModel
)
from backend.schemas import ZoneScheduleUpdateRequest, ZoneScheduleCloneRequest
from shared.sync_protocol import SyncServer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
sync_server = SyncServer(batch_interval=2.0)
hw_controller = MockHardwareController(zones=settings.zone_names)
zone_service: ZoneService = None
event_service: EventService = None
auto_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    global zone_service, event_service, auto_task

    logger.info("🔧 Initializing Pi Controller...")

    # Initialize database
    init_db()

    # Create services
    event_service = EventService()
    zone_service = ZoneService(hw_controller, event_service)

    # Initialize zones if database is empty
    zones = zone_service.list_zones(include_boiler=True)
    if not zones:
        logger.info("📦 Initializing zones in database...")
        for zone_name in settings.zone_names:
            try:
                zone_service.get_zone_status(zone_name)
            except:
                pass  # Zone will be auto-created on first access
        logger.info(f"✅ Initialized {len(settings.zone_names)} zones")

    # Register command handlers
    sync_server.register_command_handler("zone_command", handle_zone_command)
    sync_server.register_command_handler("zone_update", handle_zone_update)
    sync_server.register_command_handler("uniform_setpoint", handle_uniform_setpoint)

    # Start auto-control loop
    auto_task = asyncio.create_task(auto_control_loop())

    # Start temperature sampling loop
    temp_task = asyncio.create_task(temperature_sampling_loop())

    # Start batch sender
    batch_task = asyncio.create_task(batch_sender_loop())

    logger.info("✅ Pi Controller started")

    yield

    # Shutdown
    logger.info("🛑 Shutting down Pi Controller...")
    if auto_task:
        auto_task.cancel()
    if temp_task:
        temp_task.cancel()
    if batch_task:
        batch_task.cancel()


app = FastAPI(title="Boiler Pi Controller", version="0.1.0", lifespan=lifespan)


# Command handlers

async def handle_zone_command(payload: dict) -> dict:
    """Handle zone command from NAS."""
    zone_name = payload["zone_name"]
    command_data = payload["command_data"]

    cmd_request = ZoneCommandRequest(**command_data)
    updated_zone = zone_service.command_zone(zone_name, cmd_request)

    # Queue state update
    zones = [zone.model_dump(by_alias=True) for zone in zone_service.list_zones()]
    sync_server.queue_state_update(zones)

    return {"zone": updated_zone.model_dump(by_alias=True)}


async def handle_zone_update(payload: dict) -> dict:
    """Handle zone update from NAS."""
    zone_name = payload["zone_name"]
    command_data = payload["command_data"]

    logger.info(f"📝 Zone update request for {zone_name}: {command_data}")
    update_req = ZoneUpdateRequest(**command_data)
    logger.info(f"📝 Parsed request: target_setpoint_f={update_req.target_setpoint_f}, control_mode={update_req.control_mode}")
    updated_zone = zone_service.update_zone(zone_name, update_req)
    logger.info(f"📝 Updated zone {zone_name}: TargetSetpoint_F={updated_zone.target_setpoint_f}")

    # If zone is in AUTO mode and setpoint was updated, immediately check if state needs to change
    zone_row = repositories.get_zone_status(zone_name)
    if zone_row and zone_row.get("ControlMode") == "AUTO" and update_req.target_setpoint_f is not None:
        logger.info(f"🤖 Triggering immediate auto-control check for {zone_name}")
        zone_service.tick_auto_control()
        # Get fresh zone data after auto-control check
        updated_zone = zone_service.get_zone(zone_name)

    # Queue state update
    zones = [zone.model_dump(by_alias=True) for zone in zone_service.list_zones()]
    sync_server.queue_state_update(zones)

    return {"zone": updated_zone.model_dump(by_alias=True)}


async def handle_uniform_setpoint(payload: dict) -> dict:
    """Handle uniform setpoint from NAS."""
    command_data = payload["command_data"]

    req = UniformSetpointRequest(**command_data)
    zones = zone_service.set_uniform_setpoint(req.setpoint_f)

    # Queue state update
    zone_dicts = [zone.model_dump(by_alias=True) for zone in zones]
    sync_server.queue_state_update(zone_dicts)

    return {"zones": zone_dicts}


# Temperature sampling loop

async def temperature_sampling_loop():
    """
    Periodically read temperatures from hardware and update database.
    Publishes state updates via WebSocket.
    """
    logger.info("🌡️  Temperature sampling loop started")

    while True:
        try:
            await asyncio.sleep(30)  # Sample every 30 seconds

            updated_zones = []
            for zone_name in settings.zone_names:
                try:
                    # Read temperatures from hardware
                    room_temp = hw_controller.read_zone_temperature(zone_name)
                    pipe_temp = hw_controller.read_pipe_temperature(zone_name)

                    # Update database
                    repositories.update_zone_status(
                        zone_name=zone_name,
                        zone_room_temp_f=room_temp,
                        pipe_temp_f=pipe_temp,
                    )

                    # Get updated zone for sync
                    zone = zone_service.get_zone(zone_name)
                    if zone:
                        updated_zones.append(zone.model_dump(by_alias=True))

                except Exception as e:
                    logger.exception(f"Temperature sampling failed for {zone_name}: {e}")

            # Queue updates if we read any temps
            if updated_zones:
                sync_server.queue_state_update(updated_zones)

        except asyncio.CancelledError:
            logger.info("Temperature sampling loop cancelled")
            break
        except Exception as e:
            logger.exception(f"Temperature sampling loop error: {e}")


# Auto-control loop

async def auto_control_loop():
    """
    Run auto-control logic periodically to manage AUTO mode zones.
    Checks temperature vs setpoint and turns zones ON/OFF as needed.
    """
    logger.info("🤖 Auto-control loop started")

    while True:
        try:
            await asyncio.sleep(10)  # Check every 10 seconds for responsiveness

            # Run the zone service tick_auto_control method
            # This checks all AUTO zones and adjusts their state
            zone_service.tick_auto_control()

            # Get all zones to sync any state changes
            zones = zone_service.list_zones(include_boiler=False)
            if zones:
                zone_dicts = [zone.model_dump(by_alias=True) for zone in zones]
                sync_server.queue_state_update(zone_dicts)

        except asyncio.CancelledError:
            logger.info("🤖 Auto-control loop cancelled")
            break
        except Exception as e:
            logger.exception(f"Auto-control loop error: {e}")


async def batch_sender_loop():
    """Send batched state updates to connected clients."""
    update_counter = 0
    while True:
        try:
            await asyncio.sleep(sync_server.batch_interval)

            if sync_server.connected_clients:
                disconnected = set()

                for websocket in sync_server.connected_clients:
                    try:
                        # Send batched updates if available
                        if sync_server.batch_buffer:
                            await sync_server.send_batched_updates(websocket.send_text)
                        else:
                            # Send periodic full sync to keep cache fresh (every 5 seconds)
                            update_counter += 1
                            if update_counter >= 5:
                                zones = [zone.model_dump(by_alias=True) for zone in zone_service.list_zones()]
                                full_sync = {
                                    "event_type": "full_sync_response",
                                    "timestamp": datetime.utcnow().isoformat() + "Z",
                                    "sequence_id": sync_server.next_sequence(),
                                    "payload": {
                                        "zones": zones,
                                        "system": {"OutsideTemp_F": None, "UpdatedAt": ""},
                                        "recent_events": [],
                                        "current_sequence": sync_server.sequence_id
                                    }
                                }
                                await websocket.send_text(sync_server.serialize_message(full_sync))
                                update_counter = 0
                    except Exception as e:
                        logger.error(f"Failed to send to client: {e}")
                        disconnected.add(websocket)

                # Remove disconnected clients
                sync_server.connected_clients -= disconnected

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception(f"Batch sender error: {e}")


# WebSocket endpoint

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for NAS dashboard to subscribe to state updates."""
    await websocket.accept()
    sync_server.connected_clients.add(websocket)
    logger.info(f"WebSocket client connected. Total: {len(sync_server.connected_clients)}")

    try:
        # Send full sync on connect
        zones = [zone.model_dump(by_alias=True) for zone in zone_service.list_zones()]
        logger.info(f"Sending full_sync with {len(zones)} zones")
        full_sync = {
            "event_type": "full_sync_response",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "sequence_id": sync_server.next_sequence(),
            "payload": {
                "zones": zones,
                "system": {"OutsideTemp_F": None, "UpdatedAt": ""},
                "recent_events": [],
                "current_sequence": sync_server.sequence_id
            }
        }
        message_text = sync_server.serialize_message(full_sync)
        logger.debug(f"Message text: {message_text[:200]}...")
        await websocket.send_text(message_text)
        logger.info("✅ Full sync sent")

        # Listen for commands
        while True:
            data = await websocket.receive_text()
            message = sync_server.deserialize_message(data)

            if message["event_type"] == "command_request":
                response = await sync_server.handle_command(message)
                await websocket.send_text(sync_server.serialize_message(response))
            elif message["event_type"] == "heartbeat":
                # Respond to heartbeat
                pong = sync_server.create_message("heartbeat", {
                    "status": "healthy",
                    "uptime_seconds": 0,  # TODO: track uptime
                    "last_event_sequence": sync_server.sequence_id,
                    "database_size_mb": 0,
                    "memory_usage_mb": 0
                })
                await websocket.send_text(sync_server.serialize_message(pong))

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
    finally:
        sync_server.connected_clients.discard(websocket)


# Health endpoint

@app.get("/health")
def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "connected_clients": len(sync_server.connected_clients),
        "sequence_id": sync_server.sequence_id,
        "batch_queue_size": len(sync_server.batch_buffer)
    }


# Local REST API endpoints for hardware data collection

@app.post("/api/zones/{zone_name}/events")
def zone_event(zone_name: str, payload: ZoneEventPayload):
    """Record zone event from hardware collector."""
    event_service.log_zone_event(zone_name, payload)

    # Queue for sync
    zone = zone_service.get_zone(zone_name)
    if zone:
        sync_server.queue_state_update([zone.model_dump(by_alias=True)])

    return {"status": "ok"}


@app.post("/api/boiler/events")
def boiler_event(payload: BoilerEventPayload):
    """Record boiler event."""
    event_service.log_boiler_event(payload)
    return {"status": "ok"}


@app.post("/api/zones/history/batch")
def zone_history_batch(
    payload: ZoneHistoryBatchRequest,
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(2000, ge=10, le=12000),
    day: Optional[str] = Query(None),
    tz: str = Query("America/Denver"),
    span_days: int = Query(1, ge=1, le=31),
    max_samples: int = Query(4000, ge=200, le=20000),
):
    """Get historical data for multiple zones (batch)."""
    try:
        histories = zone_service.get_zones_history_batch(
            payload.zones,
            hours=hours,
            limit=limit,
            day=day,
            tz=tz,
            span_days=span_days,
            max_samples=max_samples,
        )
        return {"histories": histories}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/zones/stats")
def get_zone_stats(
    window: str = Query("day", pattern="^(day|week|month)$"),
    day: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
):
    """Get zone statistics for a time window."""
    try:
        return zone_service.get_zone_statistics(window=window, day=day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/events")
def list_events(
    source: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = Query(200, ge=1, le=2000)
):
    """Get event log entries."""
    return event_service.list_events(
        source=source,
        since=since,
        until=until,
        limit=limit
    )


@app.get("/api/zones/{zone_name}/history")
def get_zone_history(
    zone_name: str,
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(2000, ge=10, le=12000),
    day: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    tz: str = Query("America/Denver"),
    span_days: int = Query(1, ge=1, le=31),
    max_samples: int = Query(4000, ge=200, le=20000)
):
    """Get zone history for graphing."""
    try:
        return zone_service.get_zone_history(
            zone_name,
            hours=hours,
            limit=limit,
            day=day,
            tz=tz,
            span_days=span_days,
            max_samples=max_samples
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/zones/{zone_name}/schedule")
def get_zone_schedule(
    zone_name: str,
    include_global: bool = Query(False),
):
    """Get zone schedule."""
    try:
        return zone_service.get_zone_schedule(zone_name, include_global=include_global)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.put("/api/zones/{zone_name}/schedule")
def update_zone_schedule(
    zone_name: str,
    payload: ZoneScheduleUpdateRequest,
):
    """Update zone schedule."""
    try:
        return zone_service.update_zone_schedule(zone_name, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/zones/{zone_name}/schedule/clone")
def clone_zone_schedule(
    zone_name: str,
    payload: ZoneScheduleCloneRequest,
):
    """Clone zone schedule to other zones."""
    try:
        return zone_service.clone_zone_schedule(zone_name, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/schedule/default")
def get_default_schedule():
    """Get default/global schedule."""
    return zone_service.get_global_schedule()


@app.get("/api/schedule/presets")
def list_presets():
    """List all schedule presets."""
    return zone_service.list_schedule_presets()


@app.post("/api/schedule/presets", status_code=201)
def create_preset(payload: SchedulePresetCreateRequest):
    """Create a new schedule preset."""
    try:
        return zone_service.create_schedule_preset(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/schedule/presets/{preset_id}")
def get_preset(preset_id: int):
    """Get a specific schedule preset."""
    try:
        return zone_service.get_schedule_preset(preset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.put("/api/schedule/presets/{preset_id}")
def update_preset(preset_id: int, payload: SchedulePresetUpdateRequest):
    """Update a schedule preset."""
    try:
        return zone_service.update_schedule_preset(preset_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/schedule/presets/{preset_id}")
def delete_preset(preset_id: int):
    """Delete a schedule preset."""
    try:
        zone_service.delete_schedule_preset(preset_id)
        return {"status": "deleted"}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


if __name__ == "__main__":
    uvicorn.run(
        "pi_main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info"
    )
