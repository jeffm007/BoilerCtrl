"""
FastAPI application entry point.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import settings
from .database import init_db
from .hardware import MockHardwareController
from .schemas import (
    BoilerEventPayload,
    EventLogModel,
    GlobalScheduleUpdateRequest,
    SchedulePresetCreateRequest,
    SchedulePresetDetailModel,
    SchedulePresetSummaryModel,
    SchedulePresetUpdateRequest,
    SystemStatusModel,
    ZoneCommandRequest,
    ZoneHistoryBatchRequest,
    ZoneHistoryBatchResponse,
    ZoneScheduleCloneRequest,
    ZoneScheduleEntryModel,
    ZoneScheduleUpdateRequest,
    ZoneEventPayload,
    ZoneStatisticsModel,
    ZoneStatusModel,
    ZoneUpdateRequest,
    UniformSetpointRequest,
)
from .services import EventService, ZoneService

request_logger = logging.getLogger("boiler.requests")

# Best-effort timezone support for startup logging
try:  # Python 3.9+
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # type: ignore
except Exception:  # pragma: no cover - Python < 3.9
    try:
        from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # type: ignore
    except Exception:  # pragma: no cover - zoneinfo unavailable entirely
        ZoneInfo = None  # type: ignore
        ZoneInfoNotFoundError = Exception  # type: ignore


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
            except Exception as exc:  # log and keep the loop alive
                logging.getLogger(__name__).exception("auto_control_loop error: %s", exc)
            await asyncio.sleep(interval)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start_time
        request_logger.info(
            "http path=%s status=%s duration=%.3fs",
            request.url.path,
            response.status_code,
            duration,
        )
        return response

    @app.on_event("startup")
    async def startup_event() -> None:
        # Ensure schema exists before handling any HTTP requests.
        init_db()
        # Store service objects on the app state for dependency injection.
        app.state.zone_service = zone_service
        app.state.event_service = event_service
        app.state.auto_task = asyncio.create_task(auto_control_loop())
        # Determine active timezone (with graceful fallback for Windows without tzdata)
        configured_tz = settings.time_zone
        tz_active = configured_tz
        tz_note = "ok"
        if ZoneInfo:
            try:
                ZoneInfo(configured_tz)
            except Exception:
                # try UTC, else local-naive
                try:
                    ZoneInfo("UTC")
                    tz_active = "UTC"
                    tz_note = "fallback:UTC"
                except Exception:
                    tz_active = "LOCAL-NAIVE"
                    tz_note = "fallback:local"
        else:
            tz_active = "LOCAL-NAIVE"
            tz_note = "fallback:local"
        app.state.time_zone_active = tz_active
        print(f"Time zone configured={configured_tz} active={tz_active} note={tz_note}")
        print('Routes available:', [route.path for route in app.routes])

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        task = getattr(app.state, "auto_task", None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

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
            {
                "zone": zone.zone_name,
                "room": zone.room_name or zone.zone_name,
            }
            for zone in zone_status
            if zone.zone_name != "Boiler"
        ]
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "zones": zone_status,
                "system": system_status,
                "zone_choices": selectable_zones,
                "active_page": "dashboard",
            },
        )

    @app.get("/graphs", response_class=HTMLResponse)
    async def graphs(request: Request) -> HTMLResponse:
        zone_status = zone_service.list_zones(include_boiler=False)
        system_status = zone_service.get_system_status()
        selectable_zones = [
            {
                "zone": zone.zone_name,
                "room": zone.room_name or zone.zone_name,
            }
            for zone in zone_status
        ]
        return templates.TemplateResponse(
            "graphs.html",
            {
                "request": request,
                "zones": zone_status,
                "system": system_status,
                "zone_choices": selectable_zones,
                "active_page": "graphs",
            },
        )

    @app.get("/scheduler", response_class=HTMLResponse)
    async def scheduler_page(request: Request) -> HTMLResponse:
        zone_status = zone_service.list_zones(include_boiler=True)
        selectable_zones = [
            {
                "zone": zone.zone_name,
                "room": zone.room_name or zone.zone_name,
            }
            for zone in zone_status
            if zone.zone_name != "Boiler"
        ]
        return templates.TemplateResponse(
            "scheduler.html",
            {
                "request": request,
                "zones": zone_status,
                "zone_choices": selectable_zones,
                "active_page": "scheduler",
            },
        )

    @app.get("/metrics", response_class=HTMLResponse)
    async def metrics_page(request: Request) -> HTMLResponse:
        zone_status = zone_service.list_zones(include_boiler=False)
        selectable_zones = [
            {
                "zone": zone.zone_name,
                "room": zone.room_name or zone.zone_name,
            }
            for zone in zone_status
        ]
        system_status = zone_service.get_system_status()
        return templates.TemplateResponse(
            "metrics.html",
            {
                "request": request,
                "zones": zone_status,
                "system": system_status,
                "zone_choices": selectable_zones,
                "active_page": "metrics",
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
        window: str = Query("day", pattern="^(day|week|month)$"),
        day: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
        svc: ZoneService = Depends(get_zone_service),
    ) -> List[ZoneStatisticsModel]:
        try:
            return svc.get_zone_statistics(window=window, day=day)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

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

    @app.get(
        "/api/zones/{zone_name}/schedule", response_model=List[ZoneScheduleEntryModel]
    )
    async def api_get_zone_schedule(
        zone_name: str,
        include_global: bool = Query(False),
        svc: ZoneService = Depends(get_zone_service),
    ) -> List[ZoneScheduleEntryModel]:
        try:
            return svc.get_zone_schedule(zone_name, include_global=include_global)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    @app.put(
        "/api/zones/{zone_name}/schedule", response_model=List[ZoneScheduleEntryModel]
    )
    async def api_update_zone_schedule(
        zone_name: str,
        payload: ZoneScheduleUpdateRequest,
        svc: ZoneService = Depends(get_zone_service),
    ) -> List[ZoneScheduleEntryModel]:
        try:
            return svc.update_zone_schedule(zone_name, payload)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @app.post("/api/zones/{zone_name}/schedule/clone", response_model=List[str])
    async def api_clone_zone_schedule(
        zone_name: str,
        payload: ZoneScheduleCloneRequest,
        svc: ZoneService = Depends(get_zone_service),
    ) -> List[str]:
        try:
            return svc.clone_zone_schedule(zone_name, payload)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @app.get("/api/schedule/default", response_model=List[ZoneScheduleEntryModel])
    async def api_get_default_schedule(
        svc: ZoneService = Depends(get_zone_service),
    ) -> List[ZoneScheduleEntryModel]:
        return svc.get_global_schedule()

    @app.post("/api/zones/mode/away", response_model=List[ZoneStatusModel])
    async def api_apply_away_mode(
        payload: UniformSetpointRequest,
        svc: ZoneService = Depends(get_zone_service),
    ) -> List[ZoneStatusModel]:
        return svc.apply_uniform_setpoint(payload.setpoint_f)

    @app.post("/api/zones/mode/home", response_model=List[ZoneStatusModel])
    async def api_apply_home_mode(
        payload: UniformSetpointRequest,
        svc: ZoneService = Depends(get_zone_service),
    ) -> List[ZoneStatusModel]:
        return svc.apply_uniform_setpoint(payload.setpoint_f)

    @app.post("/api/zones/mode/schedule", response_model=List[ZoneStatusModel])
    async def api_resume_schedule_mode(
        svc: ZoneService = Depends(get_zone_service),
    ) -> List[ZoneStatusModel]:
        return svc.resume_schedule_mode()

    @app.put("/api/schedule/default", response_model=List[ZoneScheduleEntryModel])
    async def api_update_default_schedule(
        payload: GlobalScheduleUpdateRequest,
        svc: ZoneService = Depends(get_zone_service),
    ) -> List[ZoneScheduleEntryModel]:
        try:
            return svc.update_global_schedule(payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    @app.post(
        "/api/schedule/apply-global",
        response_model=List[str],
    )
    async def api_apply_global_schedule_to_auto_zones(
        svc: ZoneService = Depends(get_zone_service),
    ) -> List[str]:
        return svc.apply_global_schedule_to_auto_zones()

    @app.get(
        "/api/schedule/presets",
        response_model=List[SchedulePresetSummaryModel],
    )
    async def api_list_presets(
        svc: ZoneService = Depends(get_zone_service),
    ) -> List[SchedulePresetSummaryModel]:
        return svc.list_schedule_presets()

    @app.post(
        "/api/schedule/presets",
        response_model=SchedulePresetDetailModel,
        status_code=status.HTTP_201_CREATED,
    )
    async def api_create_preset(
        payload: SchedulePresetCreateRequest,
        svc: ZoneService = Depends(get_zone_service),
    ) -> SchedulePresetDetailModel:
        try:
            return svc.create_schedule_preset(payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @app.get(
        "/api/schedule/presets/{preset_id}",
        response_model=SchedulePresetDetailModel,
    )
    async def api_get_preset(
        preset_id: int,
        svc: ZoneService = Depends(get_zone_service),
    ) -> SchedulePresetDetailModel:
        try:
            return svc.get_schedule_preset(preset_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    @app.put(
        "/api/schedule/presets/{preset_id}",
        response_model=SchedulePresetDetailModel,
    )
    async def api_update_preset(
        preset_id: int,
        payload: SchedulePresetUpdateRequest,
        svc: ZoneService = Depends(get_zone_service),
    ) -> SchedulePresetDetailModel:
        try:
            return svc.update_schedule_preset(preset_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    @app.delete("/api/schedule/presets/{preset_id}")
    async def api_delete_preset(
        preset_id: int,
        svc: ZoneService = Depends(get_zone_service),
    ) -> Response:
        try:
            svc.delete_schedule_preset(preset_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/system", response_model=SystemStatusModel)
    async def api_system_status(
        svc: ZoneService = Depends(get_zone_service),
    ) -> SystemStatusModel:
        return svc.get_system_status()

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
        try:
            return svc.get_zone_history(
                zone_name,
                hours=hours,
                limit=limit,
                day=day,
                tz=tz,
                span_days=span_days,
                max_samples=max_samples,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

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
        try:
            histories = svc.get_zones_history_batch(
                payload.zones,
                hours=hours,
                limit=limit,
                day=day,
                tz=tz,
                span_days=span_days,
                max_samples=max_samples,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        return ZoneHistoryBatchResponse(histories=histories)

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

    return app


# Uvicorn expects a module-level variable named "app".
app = create_app()
