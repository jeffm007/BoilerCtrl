"""
FastAPI application entry point.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import settings
from .database import init_db
from .hardware import MockHardwareController
from .schemas import (
    BoilerEventPayload,
    EventLogModel,
    SystemStatusModel,
    ZoneCommandRequest,
    ZoneEventPayload,
    ZoneHistoryBatchRequest,
    ZoneHistoryBatchResponse,
    ZoneStatisticsModel,
    ZoneStatusModel,
    ZoneUpdateRequest,
)
from .services import EventService, ZoneService


def create_app() -> FastAPI:
    """
    Build and configure the FastAPI application. We keep everything in this
    factory so Uvicorn (and unit tests) can import `app` without side effects.
    """
    app = FastAPI(title="Boiler Controller", version="0.1.0")

    templates = Jinja2Templates(directory="frontend/templates")
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

    # For now we instantiate the mock hardware layer. Swap this out for a
    # GPIO-specific implementation when deploying to the Raspberry Pi.
    hardware = MockHardwareController(settings.zone_names)
    event_service = EventService()
    zone_service = ZoneService(hardware=hardware, event_service=event_service)

    async def auto_control_loop() -> None:
        """Background task that reevaluates AUTO zones periodically."""
        interval = 10  # seconds
        await asyncio.sleep(2)  # short delay before first run
        while True:
            try:
                zone_service.tick_auto_control()
            except Exception:  # noqa: BLE001 - log and keep the loop alive
                pass
            await asyncio.sleep(interval)

    @app.on_event("startup")
    async def startup_event() -> None:
        # Ensure schema exists before handling any HTTP requests.
        init_db()
        # Store service objects on the app state for dependency injection.
        app.state.zone_service = zone_service
        app.state.event_service = event_service
        app.state.auto_task = asyncio.create_task(auto_control_loop())
        app.state.cache_warm_task = asyncio.create_task(
            asyncio.to_thread(zone_service.preload_history_cache, settings.time_zone)
        )
        print('Routes available:', [route.path for route in app.routes])

    def get_zone_service() -> ZoneService:
        svc: ZoneService = app.state.zone_service
        return svc

    def get_event_service() -> EventService:
        svc: EventService = app.state.event_service
        return svc

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        zone_status = zone_service.list_zones(include_boiler=True)
        system_status = zone_service.get_system_status()
        selectable_zones = [
            zone.zone_name for zone in zone_status if zone.zone_name != "Boiler"
        ]
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "zones": zone_status,
                "system": system_status,
                "zone_choices": selectable_zones,
            },
        )

    @app.get("/api/zones", response_model=List[ZoneStatusModel])
    async def api_list_zones(
        include_boiler: bool = Query(False),
        svc: ZoneService = Depends(get_zone_service),
    ) -> List[ZoneStatusModel]:
        # When include_boiler is true the response also contains the boiler row.
        return svc.list_zones(include_boiler=include_boiler)

    @app.get("/api/zones/stats", response_model=List[ZoneStatisticsModel])
    async def api_zone_stats(
        svc: ZoneService = Depends(get_zone_service),
    ) -> List[ZoneStatisticsModel]:
        return svc.get_zone_statistics()

    @app.get("/api/zones/{zone_name}", response_model=ZoneStatusModel)
    async def api_get_zone(
        zone_name: str, svc: ZoneService = Depends(get_zone_service)
    ) -> ZoneStatusModel:
        try:
            return svc.get_zone(zone_name)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    @app.patch("/api/zones/{zone_name}", response_model=ZoneStatusModel)
    async def api_update_zone(
        zone_name: str,
        payload: ZoneUpdateRequest,
        svc: ZoneService = Depends(get_zone_service),
    ) -> ZoneStatusModel:
        try:
            return svc.update_zone(zone_name, payload)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    @app.post("/api/zones/{zone_name}/command", response_model=ZoneStatusModel)
    async def api_command_zone(
        zone_name: str,
        payload: ZoneCommandRequest,
        svc: ZoneService = Depends(get_zone_service),
    ) -> ZoneStatusModel:
        try:
            return svc.command_zone(zone_name, payload)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @app.post("/api/zones/{zone_name}/events", response_model=ZoneStatusModel)
    async def api_zone_event(
        zone_name: str,
        payload: ZoneEventPayload,
        svc: ZoneService = Depends(get_zone_service),
    ) -> ZoneStatusModel:
        try:
            # Collector scripts call this endpoint whenever a zone toggles.
            return svc.handle_zone_event(
                zone_name=zone_name,
                event=payload.event,
                zone_room_temp_f=payload.zone_room_temp_f,
                pipe_temp_f=payload.pipe_temp_f,
                outside_temp_f=payload.outside_temp_f,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    @app.post("/api/boiler/events", response_model=ZoneStatusModel)
    async def api_boiler_event(
        payload: BoilerEventPayload,
        svc: ZoneService = Depends(get_zone_service),
    ) -> ZoneStatusModel:
        return svc.handle_boiler_event(
            event=payload.event,
            outside_temp_f=payload.outside_temp_f,
        )

    @app.get("/api/system", response_model=SystemStatusModel)
    async def api_system_status(
        svc: ZoneService = Depends(get_zone_service),
    ) -> SystemStatusModel:
        return svc.get_system_status()

    @app.get("/api/events", response_model=List[EventLogModel])
    async def api_events(
        source: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = Query(200, ge=1, le=2000),
        svc: EventService = Depends(get_event_service),
    ) -> List[EventLogModel]:
        return svc.list_events(
            source=source,
            since=since,
            until=until,
            limit=limit,
        )

    @app.get("/api/zones/{zone_name}/history", response_model=List[EventLogModel])
    async def api_zone_history(
        zone_name: str,
        hours: int = Query(24, ge=1, le=720),
        limit: int = Query(2000, ge=10, le=12000),
        day: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
        tz: str = Query("America/Denver"),
        span_days: int = Query(1, ge=1, le=31),
        max_samples: int = Query(4000, ge=200, le=20000),
        svc: ZoneService = Depends(get_zone_service),
    ) -> List[EventLogModel]:
        return svc.get_zone_history(
            zone_name,
            hours=hours,
            limit=limit,
            day=day,
            tz=tz,
            span_days=span_days,
            max_samples=max_samples,
        )

    @app.post("/api/zones/history/batch", response_model=ZoneHistoryBatchResponse)
    async def api_zone_history_batch(
        payload: ZoneHistoryBatchRequest,
        hours: int = Query(24, ge=1, le=720),
        limit: int = Query(2000, ge=10, le=12000),
        day: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
        tz: str = Query("America/Denver"),
        span_days: int = Query(1, ge=1, le=31),
        max_samples: int = Query(4000, ge=200, le=20000),
        svc: ZoneService = Depends(get_zone_service),
    ) -> ZoneHistoryBatchResponse:
        histories = svc.get_zones_history_batch(
            payload.zones,
            hours=hours,
            limit=limit,
            day=day,
            tz=tz,
            span_days=span_days,
            max_samples=max_samples,
        )
        return ZoneHistoryBatchResponse(histories=histories)

    return app


# Uvicorn expects a module-level variable named "app".
app = create_app()
