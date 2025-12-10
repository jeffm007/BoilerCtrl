"""
Zone orchestration logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional, Tuple, Set
import logging
import time

try:  # Python 3.9+
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python < 3.9
    from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # type: ignore[assignment]

from .. import repositories
from ..config import settings
from ..hardware import BaseHardwareController
from ..schemas import (
    EventLogModel,
    GlobalScheduleUpdateRequest,
    SchedulePresetCreateRequest,
    SchedulePresetDetailModel,
    SchedulePresetSummaryModel,
    SchedulePresetUpdateRequest,
    SystemStatusModel,
    ZoneCommandRequest,
    ZoneScheduleCloneRequest,
    ZoneScheduleEntryModel,
    ZoneScheduleUpdateRequest,
    ZoneStatisticsModel,
    ZoneStatusModel,
    ZoneUpdateRequest,
)
from .event_service import EventService

logger = logging.getLogger(__name__)


def _normalize_row_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize database row keys for consistent access.
    SQLite preserves case, so this is mostly a pass-through.
    """
    if not row:
        return row

    # SQLite already returns proper case, no mapping needed
    return row


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO or SQLite-style timestamps into datetime objects."""
    if not value:
        return None
    normalized = value.replace(" ", "T")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _split_timestamp(value: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not value:
        return None, None
    # Handle datetime objects
    if hasattr(value, 'isoformat'):
        value = value.isoformat()
    # Convert to string if it's not already
    value = str(value)
    normalized = value.replace(" ", "T")
    parts = normalized.split("T")
    date_part = parts[0] if parts else None
    time_part = parts[1] if len(parts) > 1 else None
    if time_part:
        time_part = time_part.replace("Z", "")
        if "." in time_part:
            time_part = time_part.split(".")[0]
    return date_part, time_part


class ZoneService:
    """
    Coordinates higher-level operations: database updates, hardware control,
    and event logging. The FastAPI layer calls into this service so the web
    layer can stay very thin.
    """

    _zones_without_setpoint: Set[str] = {"Z14"}

    def __init__(
        self,
        hardware: BaseHardwareController,
        event_service: EventService,
    ) -> None:
        self.hardware = hardware
        self.events = event_service
        self._last_sample: Dict[str, datetime] = {}
        self._sample_interval = timedelta(minutes=1)
        self._schedule_backup: Dict[str, List[Dict[str, Any]]] = {}
        self._comfort_override: Set[str] = set()
        self._history_cache: Dict[str, Tuple[float, List[EventLogModel]]] = {}
        self._history_cache_lock = Lock()
        self._history_cache_ttl = 300.0  # seconds for generic windows
        self._history_cache_day_ttl = 6 * 3600.0  # day/week/month data changes slowly
        self._history_cache_hours_ttl = 600.0  # rolling windows still benefit from cache
        self._history_batch_cache: Dict[str, Tuple[float, Dict[str, List[EventLogModel]]]] = {}
        self._history_batch_lock = Lock()
        self._history_batch_ttl = 180.0

    def preload_history_cache(self, tz: Optional[str] = None) -> None:
        timezone_name = tz or settings.time_zone
        try:
            tzinfo = ZoneInfo(timezone_name)
        except Exception:
            return
        zone_names = [
            zone for zone in settings.zone_names if zone and zone.upper() != "BOILER"
        ]
        if not zone_names:
            return
        today = datetime.now(tzinfo).date()
        windows: List[Tuple[str, int]] = []
        for offset in range(1, 8):
            target = today - timedelta(days=offset)
            windows.append((target.strftime("%Y-%m-%d"), 1))
        for week in range(1, 3):
            target = today - timedelta(days=7 * week)
            windows.append((target.strftime("%Y-%m-%d"), 7))
        for months_back in (1, 2):
            year = today.year
            month = today.month - months_back
            while month <= 0:
                month += 12
                year -= 1
            first_day = datetime(year, month, 1, tzinfo=tzinfo).date()
            if month == 12:
                next_first = datetime(year + 1, 1, 1, tzinfo=tzinfo).date()
            else:
                next_first = datetime(year, month + 1, 1, tzinfo=tzinfo).date()
            span_days = max((next_first - first_day).days, 28)
            windows.append((first_day.strftime("%Y-%m-%d"), span_days))
        for zone in zone_names:
            for day_str, span in windows:
                try:
                    self.get_zone_history(
                        zone,
                        day=day_str,
                        tz=timezone_name,
                        span_days=span,
                        limit=self._estimate_history_limit(span_days=span),
                        max_samples=self._estimate_max_samples(span_days=span),
                    )
                except Exception:
                    continue
            for hours in (24, 24 * 7, 24 * 30):
                try:
                    self.get_zone_history(
                        zone,
                        hours=hours,
                        limit=self._estimate_history_limit(hours=hours),
                        max_samples=self._estimate_max_samples(hours=hours),
                    )
                except Exception:
                    continue


    @staticmethod
    def _overlap_seconds(
        start: datetime,
        end: datetime,
        window_start: datetime,
        window_end: datetime,
    ) -> float:
        if end <= window_start or start >= window_end:
            return 0.0
        overlap_start = max(start, window_start)
        overlap_end = min(end, window_end)
        if overlap_end <= overlap_start:
            return 0.0
        return (overlap_end - overlap_start).total_seconds()
    def list_zones(self, include_boiler: bool = False) -> List[ZoneStatusModel]:
        """
        Return zone status as Pydantic models for JSON serialization.
        """
        start_time = time.perf_counter()
        rows = (
            repositories.list_all_zone_rows()
            if include_boiler
            else repositories.list_zone_status()
        )
        processed: List[Dict[str, Any]] = []
        for row in rows:
            normalized = _normalize_row_keys(row)
            processed.append(self._decorate_row(self._sync_auto_setpoint(normalized)))
        duration = time.perf_counter() - start_time
        logger.info(
            "zones.list include_boiler=%s rows=%s duration=%.3fs",
            include_boiler,
            len(processed),
            duration,
        )
        return [ZoneStatusModel.model_validate(row) for row in processed]

    def get_zone(self, zone_name: str, sync_setpoint: bool = False) -> ZoneStatusModel:
        """
        Fetch a single zone and raise a KeyError if it does not exist.
        If sync_setpoint is True, apply schedule synchronization logic.
        """
        row = repositories.get_zone_status(zone_name)
        if not row:
            raise KeyError(f"Zone {zone_name} not found")
        normalized = _normalize_row_keys(row)
        if sync_setpoint:
            normalized = self._decorate_row(self._sync_auto_setpoint(normalized))
        else:
            normalized = self._decorate_row(normalized)
        return ZoneStatusModel.model_validate(normalized)

    def update_zone(self, zone_name: str, payload: ZoneUpdateRequest) -> ZoneStatusModel:
        """
        Persist setpoint or control-mode adjustments made from the dashboard.
        If updating setpoint while in AUTO mode, mark it as a manual override.
        Supports three override modes:
        - 'boundary': override until next schedule boundary (default)
        - 'permanent': override indefinitely
        - 'timed': override until specific datetime
        """
        # Check if this is a setpoint change in AUTO mode
        if payload.target_setpoint_f is not None:
            current = repositories.get_zone_status(zone_name)
            control_mode = current.get("ControlMode") if current else None

            if current and control_mode == "AUTO":
                # Mark as manual override with timestamp and mode
                from datetime import datetime
                override_mode = getattr(payload, 'override_mode', None) or "permanent"
                override_until = None

                # Parse override_until if in timed mode
                if override_mode == "timed" and hasattr(payload, 'override_until') and payload.override_until:
                    try:
                        override_until = datetime.fromisoformat(payload.override_until.replace("Z", "+00:00"))
                    except ValueError:
                        logger.warning(f"Invalid override_until datetime: {payload.override_until}")
                        override_mode = "boundary"  # Fallback to boundary mode

                logger.info(f"Setpoint change in AUTO mode for {zone_name}: {payload.target_setpoint_f}°F with {override_mode} override")
                repositories.update_zone_status(
                    zone_name,
                    target_setpoint_f=payload.target_setpoint_f,
                    setpoint_override_at=datetime.utcnow(),
                    setpoint_override_mode=override_mode,
                    setpoint_override_until=override_until,
                )
            else:
                logger.info(f"Setpoint change for {zone_name}: {payload.target_setpoint_f}°F (mode: {current.get('ControlMode') if current else 'unknown'})")
                repositories.update_zone_status(
                    zone_name,
                    target_setpoint_f=payload.target_setpoint_f,
                )

        if payload.control_mode is not None:
            current = repositories.get_zone_status(zone_name)
            if current:
                # Handle mode transition boundary conditions
                current_mode = current.get("ControlMode")
                new_mode = payload.control_mode

                if current_mode == "AUTO" and new_mode in ["MANUAL", "ON", "OFF"]:
                    # Transitioning from AUTO to manual mode
                    # Preserve the current effective setpoint and clear override metadata
                    current_setpoint = current.get("TargetSetpoint_F")
                    if current_setpoint is not None:
                        repositories.update_zone_status(
                            zone_name,
                            control_mode=new_mode,
                            target_setpoint_f=current_setpoint,
                            clear_override=True,
                        )
                    else:
                        repositories.update_zone_status(
                            zone_name,
                            control_mode=new_mode,
                            clear_override=True,
                        )
                elif current_mode in ["MANUAL", "ON", "OFF"] and new_mode == "AUTO":
                    # Transitioning from manual to AUTO mode
                    # Set to scheduled setpoint and clear any manual overrides
                    scheduled_setpoint = self._resolve_scheduled_setpoint(zone_name)
                    if scheduled_setpoint is not None:
                        repositories.update_zone_status(
                            zone_name,
                            control_mode=new_mode,
                            target_setpoint_f=scheduled_setpoint,
                            clear_override=True,
                        )
                    else:
                        repositories.update_zone_status(
                            zone_name,
                            control_mode=new_mode,
                            clear_override=True,
                        )
                else:
                    # No special handling needed for other transitions
                    repositories.update_zone_status(
                        zone_name,
                        control_mode=new_mode,
                    )
            else:
                repositories.update_zone_status(
                    zone_name,
                    control_mode=payload.control_mode,
                )

        return self.get_zone(zone_name)

    def command_zone(self, zone_name: str, payload: ZoneCommandRequest) -> ZoneStatusModel:
        """
        Issue manual override commands (forced ON/OFF/AUTO). AUTO means
        subsequent hardware state will be decided externally by the collector script.
        """
        timestamp = datetime.utcnow()
        duration_seconds: Optional[float] = None
        zone_row = repositories.get_zone_status(zone_name)
        if not zone_row:
            raise KeyError(f"Zone {zone_name} not found")
        previous_state = zone_row.get("CurrentState")
        previous_updated = _parse_timestamp(zone_row.get("UpdatedAt"))

        command = payload.command
        if command == "FORCE_ON":
            self.hardware.set_zone_state(zone_name, True)
            repositories.update_zone_status(
                zone_name,
                current_state="ON",
                control_mode="MANUAL",
                updated_at=timestamp,
            )
        elif command == "FORCE_OFF":
            self.hardware.set_zone_state(zone_name, False)
            repositories.update_zone_status(
                zone_name,
                current_state="OFF",
                control_mode="MANUAL",
                updated_at=timestamp,
            )
        elif command == "AUTO":
            # Hardware is released to automatic logic; we do not change output immediately.
            repositories.update_zone_status(zone_name, control_mode="AUTO")
            updated_zone = self.get_zone(zone_name)

            system_status = repositories.get_system_status()
            outside_temp = (
                system_status.get("OutsideTemp_F") if system_status else None
            )

            setpoint = updated_zone.target_setpoint_f
            room_temp = updated_zone.zone_room_temp_f
            desired_state: Optional[str] = None
            if setpoint is not None and room_temp is not None:
                lower_band = setpoint - 0.5
                if room_temp <= lower_band and updated_zone.current_state != "ON":
                    desired_state = "ON"
                elif room_temp >= setpoint and updated_zone.current_state != "OFF":
                    desired_state = "OFF"

            if desired_state:
                if desired_state == "ON":
                    self.hardware.set_zone_state(zone_name, True)
                else:
                    self.hardware.set_zone_state(zone_name, False)

                updated_zone = self.handle_zone_event(
                    zone_name=zone_name,
                    event=desired_state,
                    zone_room_temp_f=room_temp,
                    pipe_temp_f=updated_zone.pipe_temp_f,
                    outside_temp_f=outside_temp,
                )

            return updated_zone
        elif command == "THERMOSTAT":
            # Release control so external thermostat wiring can drive the zone.
            self.hardware.set_zone_state(zone_name, False)
            system_status = repositories.get_system_status()
            outside_temp = system_status.get("OutsideTemp_F") if system_status else None
            duration_seconds = None
            if previous_state == "ON" and previous_updated:
                duration_seconds = (timestamp - previous_updated).total_seconds()

            repositories.update_zone_status(
                zone_name,
                current_state="OFF",
                control_mode="THERMOSTAT",
                zone_room_temp_f=zone_row.get("ZoneRoomTemp_F"),
                pipe_temp_f=zone_row.get("PipeTemp_F"),
                updated_at=timestamp,
            )
            if previous_state == "ON":
                self.events.log_event(
                    source=zone_name,
                    event="OFF",
                    zone_room_temp_f=zone_row.get("ZoneRoomTemp_F"),
                    pipe_temp_f=zone_row.get("PipeTemp_F"),
                    outside_temp_f=outside_temp,
                    duration_seconds=duration_seconds,
                    timestamp=timestamp,
                )
            return self.get_zone(zone_name)
        else:
            raise ValueError(f"Unsupported command {command}")

        updated_row = self.get_zone(zone_name)

        if command in {"FORCE_ON", "FORCE_OFF"}:
            if command == "FORCE_OFF" and previous_state == "ON" and previous_updated:
                duration_seconds = (timestamp - previous_updated).total_seconds()

            self.events.log_event(
                source=zone_name,
                event="ON" if command == "FORCE_ON" else "OFF",
                zone_room_temp_f=updated_row.zone_room_temp_f,
                pipe_temp_f=updated_row.pipe_temp_f,
                outside_temp_f=(
                    repositories.get_system_status().get("OutsideTemp_F")
                ),
                duration_seconds=duration_seconds,
                timestamp=timestamp,
            )

        return updated_row

    def get_zone_schedule(
        self, zone_name: str, include_global: bool = False
    ) -> List[ZoneScheduleEntryModel]:
        if not repositories.get_zone_status(zone_name):
            raise KeyError(f"Zone {zone_name} not found")
        rows = repositories.list_zone_schedule(zone_name)
        if include_global and not rows:
            rows = repositories.list_global_schedule()
        return [ZoneScheduleEntryModel.model_validate(row) for row in rows]

    def update_zone_schedule(
        self, zone_name: str, payload: ZoneScheduleUpdateRequest
    ) -> List[ZoneScheduleEntryModel]:
        if not repositories.get_zone_status(zone_name):
            raise KeyError(f"Zone {zone_name} not found")

        normalized = self._normalize_request_entries(payload.entries)
        repositories.replace_zone_schedule(zone_name, normalized)
        self._refresh_auto_setpoints([zone_name])
        return self.get_zone_schedule(zone_name)

    def clone_zone_schedule(
        self, zone_name: str, payload: ZoneScheduleCloneRequest
    ) -> List[str]:
        if not repositories.get_zone_status(zone_name):
            raise KeyError(f"Zone {zone_name} not found")

        if not payload.target_zones:
            raise ValueError("target_zones must not be empty")

        entries = repositories.list_zone_schedule(zone_name)
        normalized = [
            {
                "DayOfWeek": entry["DayOfWeek"],
                "StartTime": entry["StartTime"],
                "EndTime": entry["EndTime"],
                "Setpoint_F": entry["Setpoint_F"],
                "Enabled": entry.get("Enabled", 1),
            }
            for entry in entries
        ]

        updated: List[str] = []
        seen_targets: Set[str] = set()
        for target in payload.target_zones:
            if target == zone_name or target in seen_targets:
                continue
            seen_targets.add(target)
            if not repositories.get_zone_status(target):
                raise KeyError(f"Zone {target} not found")
            repositories.replace_zone_schedule(target, normalized)
            updated.append(target)
        if updated:
            self._refresh_auto_setpoints(updated)
        return updated
    def apply_global_schedule_to_auto_zones(self) -> List[str]:
        """
        Clear zone-specific schedules so AUTO zones follow the global defaults.
        """
        updated: List[str] = []
        for row in repositories.list_zone_status():
            zone_name = row.get("ZoneName")
            if (
                not zone_name
                or row.get("ControlMode") != "AUTO"
                or zone_name in self._zones_without_setpoint
            ):
                continue
            repositories.replace_zone_schedule(zone_name, [])
            updated.append(zone_name)
        if updated:
            self._refresh_auto_setpoints(updated)
        return updated

    def apply_uniform_setpoint(self, setpoint_f: float) -> List[ZoneStatusModel]:
        timestamp = datetime.utcnow()
        changed: List[str] = []
        for zone_name in settings.zone_names:
            if zone_name in self._zones_without_setpoint:
                continue
            if not repositories.get_zone_status(zone_name):
                continue
            if zone_name not in self._comfort_override:
                original = repositories.list_zone_schedule(zone_name)
                self._schedule_backup[zone_name] = original
                self._comfort_override.add(zone_name)

            uniform_entries = [
                {
                    "DayOfWeek": day,
                    "StartTime": "00:00",
                    "EndTime": "00:00",
                    "Setpoint_F": setpoint_f,
                    "Enabled": True,
                }
                for day in range(7)
            ]
            repositories.replace_zone_schedule(zone_name, uniform_entries)
            repositories.update_zone_status(
                zone_name,
                target_setpoint_f=setpoint_f,
                control_mode="AUTO",
                updated_at=timestamp,
            )
            changed.append(zone_name)
        if changed:
            self._refresh_auto_setpoints(changed)
        return self.list_zones()

    def resume_schedule_mode(self) -> List[ZoneStatusModel]:
        timestamp = datetime.utcnow()
        auto_targets: List[str] = []
        for zone_name in settings.zone_names:
            if zone_name in self._zones_without_setpoint:
                continue
            if not repositories.get_zone_status(zone_name):
                continue
            repositories.update_zone_status(
                zone_name,
                control_mode="AUTO",
                target_setpoint_f=None,
                updated_at=timestamp,
            )
            if zone_name in self._comfort_override:
                original = self._schedule_backup.get(zone_name, [])
                repositories.replace_zone_schedule(zone_name, original)
                self._comfort_override.discard(zone_name)
                self._schedule_backup.pop(zone_name, None)
            auto_targets.append(zone_name)
        if auto_targets:
            self._refresh_auto_setpoints(auto_targets)
        return self.list_zones()

    def get_global_schedule(self) -> List[ZoneScheduleEntryModel]:
        rows = repositories.list_global_schedule()
        return [ZoneScheduleEntryModel.model_validate(row) for row in rows]

    def update_global_schedule(
        self, payload: GlobalScheduleUpdateRequest
    ) -> List[ZoneScheduleEntryModel]:
        normalized = self._normalize_request_entries(payload.entries)
        repositories.replace_global_schedule(normalized)
        self._refresh_auto_setpoints()
        return self.get_global_schedule()

    def list_schedule_presets(self) -> List[SchedulePresetSummaryModel]:
        rows = repositories.list_presets()
        return [SchedulePresetSummaryModel.model_validate(row) for row in rows]

    def get_schedule_preset(self, preset_id: int) -> SchedulePresetDetailModel:
        preset = repositories.get_preset_with_entries(preset_id)
        if not preset:
            raise KeyError(f"Preset {preset_id} not found")
        return SchedulePresetDetailModel.model_validate(preset)

    def create_schedule_preset(
        self, payload: SchedulePresetCreateRequest
    ) -> SchedulePresetDetailModel:
        logger.info(f"Creating preset '{payload.name}' with {len(payload.entries)} entries")
        try:
            normalized = self._normalize_request_entries(payload.entries)
            logger.info(f"Normalized entries: {normalized}")
            preset = repositories.create_preset(
                name=payload.name,
                description=payload.description,
                entries=normalized,
            )
            logger.info(f"Preset created successfully with ID: {preset.get('Id')}")
            return SchedulePresetDetailModel.model_validate(preset)
        except Exception as e:
            logger.exception(f"Failed to create preset '{payload.name}'")
            raise

    def update_schedule_preset(
        self, preset_id: int, payload: SchedulePresetUpdateRequest
    ) -> SchedulePresetDetailModel:
        if not repositories.get_preset_with_entries(preset_id):
            raise KeyError(f"Preset {preset_id} not found")

        if payload.name is not None or payload.description is not None:
            repositories.update_preset_metadata(
                preset_id,
                name=payload.name,
                description=payload.description,
            )

        if payload.entries is not None:
            normalized = self._normalize_request_entries(payload.entries)
            repositories.replace_preset_entries(preset_id, normalized)

        preset = repositories.get_preset_with_entries(preset_id)
        if not preset:
            raise RuntimeError("Preset missing after update")
        return SchedulePresetDetailModel.model_validate(preset)

    def delete_schedule_preset(self, preset_id: int) -> None:
        preset = repositories.get_preset_with_entries(preset_id)
        if not preset:
            raise KeyError(f"Preset {preset_id} not found")
        repositories.delete_preset(preset_id)

    def handle_zone_event(
        self,
        *,
        zone_name: str,
        event: str,
        zone_room_temp_f: Optional[float],
        pipe_temp_f: Optional[float],
        outside_temp_f: Optional[float],
    ) -> ZoneStatusModel:
        """
        Called by the collector script when it detects a zone changing state.
        Updates the current snapshot, records the event, and returns fresh data.
        """
        previous_row = repositories.get_zone_status(zone_name)
        if not previous_row:
            raise KeyError(f"Zone {zone_name} not found")
        previous_row["RoomName"] = settings.zone_room_map.get(zone_name, zone_name)
        date_part, time_part = _split_timestamp(previous_row.get("UpdatedAt"))
        previous_row["UpdatedDate"] = date_part
        previous_row["UpdatedTime"] = time_part

        timestamp = datetime.utcnow()
        duration_seconds: Optional[float] = None

        if event == "OFF":
            previous_state = previous_row.get("CurrentState")
            previous_updated = _parse_timestamp(previous_row.get("UpdatedAt"))
            if previous_state == "ON" and previous_updated:
                duration_seconds = (timestamp - previous_updated).total_seconds()

        current_state = "ON" if event == "ON" else "OFF"

        repositories.update_zone_status(
            zone_name,
            current_state=current_state,
            zone_room_temp_f=zone_room_temp_f,
            pipe_temp_f=pipe_temp_f,
            updated_at=timestamp,
        )

        if outside_temp_f is not None:
            repositories.update_system_status(
                outside_temp_f=outside_temp_f,
                updated_at=timestamp,
            )

        self.events.log_event(
            source=zone_name,
            event=event,
            zone_room_temp_f=zone_room_temp_f,
            pipe_temp_f=pipe_temp_f,
            outside_temp_f=outside_temp_f,
            duration_seconds=duration_seconds,
            timestamp=timestamp,
        )

        return self.get_zone(zone_name)

    def handle_boiler_event(
        self,
        *,
        event: str,
        outside_temp_f: Optional[float],
    ) -> ZoneStatusModel:
        """
        Boiler events behave just like zone events but without the extra temps.
        """
        previous_row = repositories.get_zone_status("Boiler")
        if not previous_row:
            raise KeyError("Boiler row missing")
        previous_row["RoomName"] = settings.zone_room_map.get("Boiler", "Boiler")
        date_part, time_part = _split_timestamp(previous_row.get("UpdatedAt"))
        previous_row["UpdatedDate"] = date_part
        previous_row["UpdatedTime"] = time_part

        timestamp = datetime.utcnow()
        duration_seconds: Optional[float] = None

        if event == "OFF":
            previous_state = previous_row.get("CurrentState")
            previous_updated = _parse_timestamp(previous_row.get("UpdatedAt"))
            if previous_state == "ON" and previous_updated:
                duration_seconds = (timestamp - previous_updated).total_seconds()

        repositories.update_zone_status(
            "Boiler",
            current_state="ON" if event == "ON" else "OFF",
            updated_at=timestamp,
        )

        if outside_temp_f is not None:
            repositories.update_system_status(
                outside_temp_f=outside_temp_f,
                updated_at=timestamp,
            )

        self.events.log_event(
            source="Boiler",
            event=event,
            zone_room_temp_f=None,
            pipe_temp_f=None,
            outside_temp_f=outside_temp_f,
            duration_seconds=duration_seconds,
            timestamp=timestamp,
        )

        return self.get_zone("Boiler")

    def get_system_status(self) -> SystemStatusModel:
        """
        Helper used by the dashboard to show outdoor temperature metadata.
        """
        start_time = time.perf_counter()
        row = repositories.get_system_status()
        duration = time.perf_counter() - start_time
        logger.info("system.status duration=%.3fs", duration)
        return SystemStatusModel.model_validate(row)

    def _ensure_auto_state(
        self,
        row: Dict[str, Any],
        outside_temp: Optional[float],
    ) -> Dict[str, Any]:
        zone_name = row.get("ZoneName")
        if not zone_name:
            return self._decorate_row(row)

        room_temp = row.get("ZoneRoomTemp_F")
        row = self._sync_auto_setpoint(row)
        setpoint = row.get("TargetSetpoint_F")

        if setpoint is None or room_temp is None:
            return self._decorate_row(row)

        current_state = row.get("CurrentState")
        lower_band = setpoint - 0.5
        desired_state: Optional[str] = None

        if room_temp is not None:
            if room_temp <= lower_band and current_state != "ON":
                desired_state = "ON"
            elif room_temp >= setpoint and current_state != "OFF":
                desired_state = "OFF"

        if desired_state is None:
            return self._decorate_row(
                self._simulate_temperature(row, outside_temp)
            )

        if desired_state == "ON":
            if room_temp >= 80.0:
                desired_state = "OFF"
            else:
                self.hardware.set_zone_state(zone_name, True)
        if desired_state == "OFF":
            if room_temp <= 50.0:
                desired_state = "ON"
            else:
                self.hardware.set_zone_state(zone_name, False)
        if desired_state == "ON":
            self.hardware.set_zone_state(zone_name, True)

        updated = self.handle_zone_event(
            zone_name=zone_name,
            event=desired_state,
            zone_room_temp_f=room_temp,
            pipe_temp_f=row.get("PipeTemp_F"),
            outside_temp_f=outside_temp,
        )

        simulated = self._simulate_temperature(
            updated.model_dump(by_alias=True), outside_temp
        )
        return self._decorate_row(simulated)

    def _simulate_temperature(
        self,
        row: Dict[str, Any],
        outside_temp: Optional[float],
    ) -> Dict[str, Any]:
        """Adjust the stored room temperature to mimic heating/cooling."""
        current_temp = row.get("ZoneRoomTemp_F")
        setpoint = row.get("TargetSetpoint_F")
        if current_temp is None or setpoint is None:
            return row

        baseline = outside_temp if outside_temp is not None else 60.0
        current_state = row.get("CurrentState")

        if current_state == "ON":
            new_temp = current_temp + 0.3
            if new_temp >= setpoint:
                new_temp = setpoint
                self.hardware.set_zone_state(row["ZoneName"], False)
                updated = self.handle_zone_event(
                    zone_name=row["ZoneName"],
                    event="OFF",
                    zone_room_temp_f=new_temp,
                    pipe_temp_f=row.get("PipeTemp_F"),
                    outside_temp_f=outside_temp,
                )
                return updated.model_dump(by_alias=True)
        else:
            drift_target = min(setpoint - 0.75, baseline)
            new_temp = current_temp - 0.2
            if new_temp <= drift_target:
                new_temp = drift_target

        rounded = round(new_temp, 1)
        if rounded != row.get("ZoneRoomTemp_F"):
            repositories.update_zone_status(
                row["ZoneName"], zone_room_temp_f=rounded
            )
        row["ZoneRoomTemp_F"] = rounded
        return row

    def _resolve_scheduled_setpoint(
        self, zone_name: str, moment: Optional[datetime] = None
    ) -> Optional[float]:
        # Avoid strict tz dependencies; operate in local time when tzdata is missing.
        entries = repositories.list_zone_schedule(zone_name)
        setpoint = self._evaluate_schedule(entries, moment, tzinfo=None)
        if setpoint is not None:
            return setpoint
        upcoming = self._next_schedule_setpoint(entries, moment, tzinfo=None)
        if upcoming is not None:
            return upcoming

        global_entries = repositories.list_global_schedule()
        setpoint = self._evaluate_schedule(global_entries, moment, tzinfo=None)
        if setpoint is not None:
            return setpoint
        return self._next_schedule_setpoint(global_entries, moment, tzinfo=None)
    def _sync_auto_setpoint(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure AUTO-controlled zones reflect the scheduled setpoint immediately.
        Respects manual overrides based on mode:
        - 'boundary': override until next schedule boundary (schedule change detected)
        - 'permanent': override indefinitely until manually cleared
        - 'timed': override until specified datetime
        """
        control_mode = row.get("ControlMode")
        zone_name = row.get("ZoneName")
        if (
            control_mode != "AUTO"
            or not zone_name
            or zone_name not in settings.zone_names
            or zone_name in self._zones_without_setpoint
        ):
            return row

        scheduled_setpoint = self._resolve_scheduled_setpoint(zone_name)
        if scheduled_setpoint is None:
            return row

        current_setpoint = row.get("TargetSetpoint_F")
        override_at = row.get("SetpointOverrideAt")
        override_mode = row.get("SetpointOverrideMode")
        override_until = row.get("SetpointOverrideUntil")

        # Check if there's a manual override active
        if override_at is not None and override_mode is not None:
            logger.info(f"Found override for {zone_name}: mode={override_mode}, at={override_at}, until={override_until}")
            from datetime import datetime

            # Handle 'timed' mode - check if override has expired
            if override_mode == "timed" and override_until is not None:
                try:
                    if isinstance(override_until, str):
                        try:
                            until_time = datetime.fromisoformat(override_until.replace('Z', '+00:00'))
                        except:
                            until_time = datetime.strptime(override_until, "%Y-%m-%d %H:%M:%S")
                    else:
                        until_time = override_until

                    # Check if override has expired (compare UTC times)
                    if datetime.utcnow() >= until_time:
                        # Override expired, clear it and apply schedule
                        repositories.update_zone_status(zone_name,
                                                       target_setpoint_f=scheduled_setpoint,
                                                       clear_override=True)
                        current_setpoint = scheduled_setpoint
                        row["TargetSetpoint_F"] = current_setpoint
                        return row
                except Exception as e:
                    logger.warning(f"Failed to parse override_until for {zone_name}: {e}")
                    # Clear malformed override
                    repositories.update_zone_status(zone_name,
                                                   target_setpoint_f=scheduled_setpoint,
                                                   clear_override=True)
                    current_setpoint = scheduled_setpoint
                    row["TargetSetpoint_F"] = current_setpoint
                    return row

            # Handle 'permanent' mode - never clear automatically
            if override_mode == "permanent":
                return row

            # Handle 'boundary' mode - clear on schedule change
            if override_mode == "boundary":
                # Check if the scheduled setpoint has changed since the override
                if current_setpoint is not None and abs(scheduled_setpoint - current_setpoint) > 0.05:
                    # Schedule has changed - this is a schedule boundary, clear override
                    repositories.update_zone_status(zone_name,
                                                   target_setpoint_f=scheduled_setpoint,
                                                   clear_override=True)
                    current_setpoint = scheduled_setpoint
                    row["TargetSetpoint_F"] = current_setpoint
                    return row
                else:
                    # Schedule hasn't changed, keep the override
                    return row

        # No override or override not applicable, apply schedule as normal
        if current_setpoint is None or abs(current_setpoint - scheduled_setpoint) > 0.05:
            logger.info(f"Applying scheduled setpoint {scheduled_setpoint} to {zone_name} (was {current_setpoint})")
            repositories.update_zone_status(zone_name, target_setpoint_f=scheduled_setpoint)
            current_setpoint = scheduled_setpoint

        if row.get("TargetSetpoint_F") != current_setpoint:
            row = dict(row)
            row["TargetSetpoint_F"] = current_setpoint
        return row

        if row.get("TargetSetpoint_F") != current_setpoint:
            row = dict(row)
            row["TargetSetpoint_F"] = current_setpoint
        return row

    def _refresh_auto_setpoints(self, zone_names: Optional[Iterable[str]] = None) -> None:
        """
        Apply scheduled setpoints to AUTO zones after schedule updates.
        """
        targets = zone_names or settings.zone_names
        for zone in targets:
            if zone in self._zones_without_setpoint:
                continue
            row = repositories.get_zone_status(zone)
            if not row or row.get("ControlMode") != "AUTO":
                continue
            self._sync_auto_setpoint(row)

    @staticmethod
    def _time_to_minutes(value: Optional[str]) -> Optional[int]:
        if not value:
            return None
        try:
            parts = value.split(":")
            if len(parts) != 2:
                return None
            hour = int(parts[0])
            minute = int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return None
            return hour * 60 + minute
        except (ValueError, TypeError):
            return None

    def tick_auto_control(self) -> None:
        system_status = repositories.get_system_status()
        outside_temp = system_status.get("OutsideTemp_F") if system_status else None
        for raw_row in repositories.list_zone_status():
            working_row = raw_row
            if raw_row.get("ControlMode") == "AUTO":
                working_row = self._ensure_auto_state(raw_row, outside_temp)
            decorated = self._decorate_row(working_row)
            self._maybe_record_sample(decorated, outside_temp)

    def _decorate_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        row = dict(row)
        row["RoomName"] = settings.zone_room_map.get(
            row.get("ZoneName", ""), row.get("ZoneName")
        )
        # Convert datetime objects to ISO format strings
        updated_at = row.get("UpdatedAt")
        if updated_at and hasattr(updated_at, 'isoformat'):
            row["UpdatedAt"] = updated_at.isoformat()
        date_part, time_part = _split_timestamp(row.get("UpdatedAt"))
        row["UpdatedDate"] = date_part
        row["UpdatedTime"] = time_part
        return row

    def get_zone_statistics(
        self,
        window: str = "day",
        day: Optional[str] = None,
    ) -> List[ZoneStatisticsModel]:
        start_time = time.perf_counter()
        window_map = {"day": 1, "week": 7, "month": 30}
        normalized_window = window.lower()
        if normalized_window not in window_map:
            raise ValueError("window must be one of: day, week, month")

        tzinfo = ZoneInfo(settings.time_zone)
        if day:
            try:
                day_dt = datetime.strptime(day, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError("day must be formatted as YYYY-MM-DD") from exc
            anchor_end_local = day_dt.replace(tzinfo=tzinfo) + timedelta(days=1)
        else:
            anchor_end_local = datetime.now(tzinfo)

        window_days = window_map[normalized_window]
        window_start_local = anchor_end_local - timedelta(days=window_days)
        month_start_local = anchor_end_local - timedelta(days=30)

        window_end_utc = anchor_end_local.astimezone(timezone.utc).replace(tzinfo=None)
        window_start_utc = window_start_local.astimezone(timezone.utc).replace(tzinfo=None)
        month_start_utc = month_start_local.astimezone(timezone.utc).replace(tzinfo=None)
        window_hours = (window_end_utc - window_start_utc).total_seconds() / 3600.0

        stats: List[ZoneStatisticsModel] = []
        for zone_name in settings.zone_names:
            status_row = repositories.get_zone_status(zone_name)
            if not status_row:
                continue

            decorated_status = self._decorate_row(status_row)
            room_name = decorated_status.get("RoomName")

            events = self.events.list_events(
                source=zone_name,
                since=month_start_utc.isoformat(),
                until=window_end_utc.isoformat(),
                limit=7000,
                include_samples=False,
            )
            calls_window, total_window_seconds, monthly_seconds, avg_run_seconds = (
                self._calculate_run_metrics(
                    events,
                    window_start_utc,
                    window_end_utc,
                    month_start_utc,
                )
            )

            sample_events = self.events.list_events(
                source=zone_name,
                since=window_start_utc.isoformat(),
                until=window_end_utc.isoformat(),
                limit=3000,
                include_samples=True,
            )
            sample_values = [
                evt.zone_room_temp_f
                for evt in sample_events
                if evt.event == "SAMPLE" and evt.zone_room_temp_f is not None
            ]
            avg_room_temp = (
                sum(sample_values) / len(sample_values)
                if sample_values
                else decorated_status.get("ZoneRoomTemp_F")
            )

            stats.append(
                ZoneStatisticsModel(
                    zone_name=zone_name,
                    room_name=room_name,
                    calls_in_window=calls_window,
                    average_run_seconds_per_call=avg_run_seconds,
                    total_run_window_seconds=total_window_seconds,
                    total_run_30day_seconds=monthly_seconds,
                    average_room_temp_f=avg_room_temp,
                    window=normalized_window,
                    window_hours=window_hours,
                    window_start=window_start_utc.isoformat(),
                    window_end=window_end_utc.isoformat(),
                )
            )

        duration = time.perf_counter() - start_time
        logger.info(
            "zones.stats window=%s day=%s rows=%s duration=%.3fs",
            window,
            day,
            len(stats),
            duration,
        )
        return stats

    def _calculate_run_metrics(
        self,
        events: List[EventLogModel],
        window_start: datetime,
        window_end: datetime,
        month_start: datetime,
    ) -> Tuple[int, float, float, float]:
        """
        Derive call counts and durations by pairing ON/OFF events.
        """
        events_sorted = sorted(events, key=lambda e: e.timestamp)

        calls_window = 0
        total_window_seconds = 0.0
        monthly_seconds = 0.0
        pending_on: Optional[datetime] = None

        for event in events_sorted:
            ts = datetime.fromisoformat(event.timestamp.replace("Z", ""))
            if event.event == "ON":
                pending_on = ts
                continue
            if event.event != "OFF":
                continue

            start = self._resolve_run_start(event, ts, pending_on)
            pending_on = None
            if start is None or start >= ts:
                continue

            monthly_overlap = self._overlap_seconds(start, ts, month_start, window_end)
            window_overlap = self._overlap_seconds(start, ts, window_start, window_end)
            monthly_seconds += monthly_overlap
            if window_overlap > 0:
                total_window_seconds += window_overlap
                calls_window += 1

        avg_run_seconds = (
            total_window_seconds / calls_window if calls_window > 0 else 0.0
        )
        return calls_window, total_window_seconds, monthly_seconds, avg_run_seconds

    @staticmethod
    def _resolve_run_start(
        event: EventLogModel,
        off_timestamp: datetime,
        pending_on: Optional[datetime],
    ) -> Optional[datetime]:
        duration = event.duration_seconds
        if duration is not None and duration >= 0:
            return off_timestamp - timedelta(seconds=duration)
        if pending_on:
            return pending_on
        return None

    def _normalize_request_entries(
        self, entries: Iterable[Any]
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        seen_keys: Set[Tuple[int, str]] = set()
        for entry in entries:
            day = getattr(entry, "day_of_week", None)
            if day is None:
                day = entry.get("day_of_week") if isinstance(entry, dict) else None
            if day is None or not 0 <= day <= 6:
                raise ValueError("day_of_week must be between 0 (Monday) and 6 (Sunday)")
            start_time = getattr(entry, "start_time", None) or (
                entry.get("start_time") if isinstance(entry, dict) else None
            )
            end_time = getattr(entry, "end_time", None) or (
                entry.get("end_time") if isinstance(entry, dict) else None
            )
            if self._time_to_minutes(start_time) is None or self._time_to_minutes(end_time) is None:
                raise ValueError("start_time and end_time must be HH:MM in 24-hour format")
            key = (day, start_time)
            if key in seen_keys:
                raise ValueError("Duplicate start_time for the same day is not allowed")
            seen_keys.add(key)
            setpoint = getattr(entry, "setpoint_f", None)
            if setpoint is None and isinstance(entry, dict):
                setpoint = entry.get("setpoint_f")
            if setpoint is None:
                raise ValueError("setpoint_f is required")
            enabled = getattr(entry, "enabled", None)
            if enabled is None and isinstance(entry, dict):
                enabled = entry.get("enabled", True)
            normalized.append(
                {
                    "DayOfWeek": day,
                    "StartTime": start_time,
                    "EndTime": end_time,
                    "Setpoint_F": float(setpoint),
                    "Enabled": bool(enabled),
                }
            )
        return normalized

    @staticmethod
    def _normalize_moment(
        moment: Optional[datetime],
        tzinfo: Optional[ZoneInfo],
    ) -> datetime:
        if tzinfo is None:
            if moment is None:
                return datetime.now()
            if moment.tzinfo is None:
                return moment
            # Convert to local naive time
            return moment.astimezone().replace(tzinfo=None)
        if moment is None:
            return datetime.now(tzinfo)
        if moment.tzinfo is None:
            return moment.replace(tzinfo=tzinfo)
        return moment.astimezone(tzinfo)

    def _evaluate_schedule(
        self,
        entries: Iterable[Dict[str, Any]],
        moment: Optional[datetime] = None,
        tzinfo: Optional[ZoneInfo] = None,
    ) -> Optional[float]:
        entries = list(entries)
        if not entries:
            return None

        now_local = self._normalize_moment(moment, tzinfo)

        day = now_local.weekday()
        minutes_now = now_local.hour * 60 + now_local.minute

        for entry in entries:
            if not entry.get("Enabled", 1):
                continue
            if entry.get("DayOfWeek") != day:
                continue
            start_minutes = self._time_to_minutes(entry.get("StartTime"))
            end_minutes = self._time_to_minutes(entry.get("EndTime"))
            if start_minutes is None or end_minutes is None:
                continue
            setpoint = entry.get("Setpoint_F")
            if start_minutes == end_minutes:
                return setpoint
            if start_minutes < end_minutes:
                if start_minutes <= minutes_now < end_minutes:
                    return setpoint
            else:  # window spans midnight
                if minutes_now >= start_minutes or minutes_now < end_minutes:
                    return setpoint
        return None

    def _next_schedule_setpoint(
        self,
        entries: Iterable[Dict[str, Any]],
        moment: Optional[datetime],
        tzinfo: Optional[ZoneInfo],
    ) -> Optional[float]:
        entries = list(entries)
        if not entries:
            return None

        now_local = self._normalize_moment(moment, tzinfo)
        # Sort entries by day then start time to ensure deterministic search.
        sorted_entries = sorted(
            entries,
            key=lambda entry: (
                int(entry.get("DayOfWeek", 0)),
                self._time_to_minutes(entry.get("StartTime")) or 0,
            ),
        )

        current_day = now_local.weekday()
        current_minutes = now_local.hour * 60 + now_local.minute

        for day_offset in range(0, 7):
            target_day = (current_day + day_offset) % 7
            for entry in sorted_entries:
                if not entry.get("Enabled", 1):
                    continue
                if int(entry.get("DayOfWeek", -1)) != target_day:
                    continue
                start_minutes = self._time_to_minutes(entry.get("StartTime"))
                if start_minutes is None:
                    continue
                if day_offset == 0 and start_minutes <= current_minutes:
                    continue
                return entry.get("Setpoint_F")
        return None

    def get_zone_history(
        self,
        zone_name: str,
        hours: int = 24,
        limit: int = 2000,
        day: Optional[str] = None,
        tz: str = "America/Denver",
        span_days: int = 1,
        max_samples: int = 4000,
    ) -> List[EventLogModel]:
        since_naive: datetime
        until_naive: Optional[datetime] = None

        cache_key: Optional[str] = None
        cache_ttl = self._history_cache_ttl
        cache_label = "miss"
        normalized_span = max(1, min(span_days, 31))
        window_desc = ""
        start_time = time.perf_counter()

        if day:
            try:
                tzinfo = ZoneInfo(tz)
            except Exception as exc:  # pragma: no cover - invalid timezone supplied
                raise ValueError(f"Unknown timezone '{tz}'") from exc
            try:
                day_dt = datetime.strptime(day, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError("day must be formatted as YYYY-MM-DD") from exc

            if self._is_history_cache_eligible(day_dt, normalized_span, tzinfo):
                cache_key = self._history_cache_key(
                    zone_name,
                    day,
                    normalized_span,
                    limit,
                    max_samples,
                )
                cache_ttl = self._history_cache_day_ttl
                cached = self._get_cached_history(cache_key)
                if cached is not None:
                    cache_label = "hit"
                    window_desc = f"day={day},span={normalized_span}"
                    logger.info(
                        "history.fetch zone=%s window=%s rows=%s duration=%.3fs cache=%s",
                        zone_name,
                        window_desc,
                        len(cached),
                        0.0,
                        cache_label,
                    )
                    return cached
            start_local = day_dt.replace(tzinfo=tzinfo)
            end_local = start_local + timedelta(days=normalized_span)
            since_naive = start_local.astimezone(timezone.utc).replace(tzinfo=None)
            until_naive = end_local.astimezone(timezone.utc).replace(tzinfo=None)
            window_desc = f"day={day},span={normalized_span}"
        else:
            if self._is_hours_cache_eligible(hours):
                cache_key = self._history_cache_key(
                    zone_name,
                    None,
                    1,
                    limit,
                    max_samples,
                    hours=hours,
                )
                cache_ttl = self._history_cache_hours_ttl
                cached = self._get_cached_history(cache_key)
                if cached is not None:
                    cache_label = "hit"
                    window_desc = f"hours={hours}"
                    logger.info(
                        "history.fetch zone=%s window=%s rows=%s duration=%.3fs cache=%s",
                        zone_name,
                        window_desc,
                        len(cached),
                        0.0,
                        cache_label,
                    )
                    return cached
            since_naive = (datetime.utcnow() - timedelta(hours=hours)).replace(
                microsecond=0
            )
            window_desc = f"hours={hours}"
        history = self.events.list_events(
            source=zone_name,
            since=since_naive.isoformat(),
            until=until_naive.isoformat() if until_naive else None,
            limit=limit,
            include_samples=True,
        )
        status_row = repositories.get_zone_status(zone_name)
        if status_row:
            decorated = self._decorate_row(status_row)
            latest_timestamp = decorated.get("UpdatedAt")
            if not latest_timestamp:
                latest_timestamp = datetime.utcnow().isoformat()
            latest_dt = _parse_timestamp(latest_timestamp)
            within_window = True
            if latest_dt:
                if until_naive and latest_dt >= until_naive:
                    within_window = False
                if latest_dt < since_naive:
                    within_window = False
            if within_window:
                history.append(
                    EventLogModel.model_validate(
                        {
                            "Id": -1,
                            "Timestamp": latest_timestamp,
                            "Source": zone_name,
                            "Event": "SAMPLE",
                            "RoomName": decorated.get("RoomName"),
                            "ZoneRoomTemp_F": decorated.get("ZoneRoomTemp_F"),
                            "PipeTemp_F": decorated.get("PipeTemp_F"),
                            "OutsideTemp_F": repositories.get_system_status().get(
                                "OutsideTemp_F"
                            )
                            if repositories.get_system_status()
                            else None,
                            "DurationSeconds": None,
                            "EventDate": decorated.get("UpdatedDate"),
                            "EventTime": decorated.get("UpdatedTime"),
                        }
                    )
                )
        history.sort(key=lambda item: item.timestamp)
        result = self._downsample_history(history, max_samples)
        if cache_key:
            self._store_history_cache(cache_key, result, cache_ttl)
        duration = time.perf_counter() - start_time
        logger.info(
            "history.fetch zone=%s window=%s rows_raw=%s rows_sent=%s limit=%s duration=%.3fs cache=%s",
            zone_name,
            window_desc or ("hours=%s" % hours),
            len(history),
            len(result),
            limit,
            duration,
            cache_label,
        )
        return result

    def get_zones_history_batch(
        self,
        zones: List[str],
        hours: int = 24,
        limit: int = 2000,
        day: Optional[str] = None,
        tz: str = "America/Denver",
        span_days: int = 1,
        max_samples: int = 4000,
    ) -> Dict[str, List[EventLogModel]]:
        normalized_zones = [
            zone.strip()
            for zone in zones
            if zone.strip() and zone.strip().upper() != "BOILER"
        ]
        if not normalized_zones:
            normalized_zones = [
                zone
                for zone in settings.zone_names
                if zone and zone.upper() != "BOILER"
            ]
        sorted_key = sorted(set(normalized_zones))
        batch_key = self._history_batch_key(
            sorted_key,
            hours=hours,
            limit=limit,
            day=day,
            tz=tz,
            span_days=span_days,
            max_samples=max_samples,
        )
        cached = self._get_cached_batch(batch_key)
        if cached is not None:
            return cached
        histories: Dict[str, List[EventLogModel]] = {}
        for zone in sorted_key:
            histories[zone] = self.get_zone_history(
                zone,
                hours=hours,
                limit=limit,
                day=day,
                tz=tz,
                span_days=span_days,
                max_samples=max_samples,
            )
        self._store_batch_cache(batch_key, histories)
        return histories

    def _downsample_history(
        self,
        history: List[EventLogModel],
        max_samples: int,
    ) -> List[EventLogModel]:
        if max_samples <= 0:
            return history
        sample_indices = [
            idx for idx, entry in enumerate(history) if entry.event == "SAMPLE"
        ]
        if len(sample_indices) <= max_samples:
            return history
        selected_indices = set()
        step = len(sample_indices) / max_samples
        position = 0.0
        for _ in range(max_samples):
            list_index = min(int(position), len(sample_indices) - 1)
            selected_indices.add(sample_indices[list_index])
            position += step
        selected_indices.add(sample_indices[0])
        selected_indices.add(sample_indices[-1])
        filtered: List[EventLogModel] = []
        for idx, entry in enumerate(history):
            if entry.event == "SAMPLE" and idx not in selected_indices:
                continue
            filtered.append(entry)
        return filtered

    @staticmethod
    def _estimate_history_limit(
        *,
        span_days: Optional[int] = None,
        hours: Optional[int] = None,
    ) -> int:
        estimated_hours: int
        if hours is not None:
            estimated_hours = max(1, int(hours))
        elif span_days is not None:
            estimated_hours = max(1, span_days) * 24
        else:
            estimated_hours = 24
        if 24 < estimated_hours < 168:
            return 6000
        if 168 <= estimated_hours < 720:
            return 8000
        if estimated_hours >= 720:
            return 12000
        return 4000

    @staticmethod
    def _estimate_max_samples(
        *,
        span_days: Optional[int] = None,
        hours: Optional[int] = None,
    ) -> int:
        if span_days is not None:
            effective_days = max(1.0, float(span_days))
        elif hours is not None:
            effective_days = max(1.0, float(hours) / 24.0)
        else:
            effective_days = 1.0
        return int(max(800, min(4000, round(effective_days * 250))))

    def _is_history_cache_eligible(
        self,
        day_dt: datetime,
        span_days: int,
        tzinfo: ZoneInfo,
    ) -> bool:
        today_local = datetime.now(tzinfo).date()
        diff_days = (today_local - day_dt.date()).days
        if diff_days < 0:
            return False
        if span_days <= 1:
            return diff_days <= 7
        if 2 <= span_days <= 9:
            return diff_days <= 14
        if span_days >= 28:
            return diff_days <= 62
        return False

    def _is_hours_cache_eligible(self, hours: int) -> bool:
        return hours in {24, 24 * 7, 24 * 14, 24 * 30}

    def _history_cache_key(
        self,
        zone_name: str,
        day: Optional[str],
        span_days: int,
        limit: int,
        max_samples: int,
        *,
        hours: Optional[int] = None,
    ) -> str:
        if day:
            return f"{zone_name}:D:{day}:{span_days}:{limit}:{max_samples}"
        if hours:
            return f"{zone_name}:H:{hours}"
        return f"{zone_name}:GEN:{span_days}:{limit}:{max_samples}"

    def _get_cached_history(self, key: str) -> Optional[List[EventLogModel]]:
        with self._history_cache_lock:
            entry = self._history_cache.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if expires_at < time.time():
                del self._history_cache[key]
                return None
            return value

    def _store_history_cache(
        self,
        key: str,
        value: List[EventLogModel],
        ttl: Optional[float] = None,
    ) -> None:
        effective_ttl = ttl if ttl is not None else self._history_cache_ttl
        expires_at = time.time() + effective_ttl
        with self._history_cache_lock:
            self._history_cache[key] = (expires_at, value)
            if len(self._history_cache) > 200:
                now = time.time()
                stale_keys = [
                    cache_key
                for cache_key, (expiry, _) in self._history_cache.items()
                    if expiry < now
                ]
                for cache_key in stale_keys:
                    self._history_cache.pop(cache_key, None)

    def _history_batch_key(
        self,
        zones: List[str],
        *,
        hours: int,
        limit: int,
        day: Optional[str],
        tz: str,
        span_days: int,
        max_samples: int,
    ) -> str:
        zones_part = ",".join(zones)
        return f"{zones_part}|{hours}|{limit}|{day or ''}|{tz}|{span_days}|{max_samples}"

    def _get_cached_batch(
        self,
        key: str,
    ) -> Optional[Dict[str, List[EventLogModel]]]:
        with self._history_batch_lock:
            entry = self._history_batch_cache.get(key)
            if not entry:
                return None
            expires_at, histories = entry
            if expires_at < time.time():
                del self._history_batch_cache[key]
                return None
            return histories

    def _store_batch_cache(
        self,
        key: str,
        histories: Dict[str, List[EventLogModel]],
    ) -> None:
        expires_at = time.time() + self._history_batch_ttl
        with self._history_batch_lock:
            self._history_batch_cache[key] = (expires_at, histories)
            if len(self._history_batch_cache) > 50:
                now = time.time()
                stale_keys = [
                    cache_key
                    for cache_key, (expiry, _) in self._history_batch_cache.items()
                    if expiry < now
                ]
                for cache_key in stale_keys:
                    self._history_batch_cache.pop(cache_key, None)

    def _maybe_record_sample(
        self,
        row: Dict[str, Any],
        outside_temp: Optional[float],
    ) -> None:
        zone_name = row.get("ZoneName")
        if not zone_name:
            return

        now = datetime.utcnow()
        last = self._last_sample.get(zone_name)
        if last and now - last < self._sample_interval:
            return

        room_temp = row.get("ZoneRoomTemp_F")
        if room_temp is None:
            return

        resolved_outside = outside_temp
        if resolved_outside is None:
            system_row = repositories.get_system_status()
            resolved_outside = system_row.get("OutsideTemp_F") if system_row else None
        pipe_temp = row.get("PipeTemp_F")

        self._last_sample[zone_name] = now
        self.events.log_event(
            source=zone_name,
            event="SAMPLE",
            zone_room_temp_f=room_temp,
            pipe_temp_f=pipe_temp,
            outside_temp_f=resolved_outside,
            duration_seconds=None,
            timestamp=now,
        )
        repositories.record_temperature_sample(
            zone_name=zone_name,
            timestamp=now,
            room_temp_f=room_temp,
            pipe_temp_f=pipe_temp,
            outside_temp_f=resolved_outside,
        )
