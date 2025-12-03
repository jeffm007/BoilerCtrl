"""
Pydantic models for request/response payloads.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class ZoneStatusModel(BaseModel):
    """
    API response representing one row in the ZoneStatus table.
    """
    model_config = ConfigDict(populate_by_name=True)

    zone_name: str = Field(..., alias="ZoneName")
    room_name: str = Field(..., alias="RoomName")
    current_state: Literal["ON", "OFF"] = Field(..., alias="CurrentState")
    zone_room_temp_f: Optional[float] = Field(None, alias="ZoneRoomTemp_F")
    pipe_temp_f: Optional[float] = Field(None, alias="PipeTemp_F")
    target_setpoint_f: Optional[float] = Field(None, alias="TargetSetpoint_F")
    control_mode: Literal["AUTO", "MANUAL", "THERMOSTAT"] = Field(
        ..., alias="ControlMode"
    )
    updated_at: str = Field(..., alias="UpdatedAt")
    updated_date: Optional[str] = Field(None, alias="UpdatedDate")
    updated_time: Optional[str] = Field(None, alias="UpdatedTime")


class SystemStatusModel(BaseModel):
    """
    Response model for the single SystemStatus row.
    """
    model_config = ConfigDict(populate_by_name=True)

    outside_temp_f: Optional[float] = Field(None, alias="OutsideTemp_F")
    updated_at: str = Field(..., alias="UpdatedAt")


class ZoneStatisticsModel(BaseModel):
    """
    Aggregate metrics for dashboard summaries.
    """
    model_config = ConfigDict(populate_by_name=True)

    zone_name: str
    room_name: Optional[str]
    calls_in_window: int
    average_run_seconds_per_call: float
    total_run_window_seconds: float
    total_run_30day_seconds: float
    average_room_temp_f: Optional[float]
    window: str
    window_hours: float
    window_start: str
    window_end: str


class UniformSetpointRequest(BaseModel):
    """Payload to set all zones to a uniform temperature."""

    setpoint_f: float


class ZoneUpdateRequest(BaseModel):
    """
    Payload accepted when the dashboard tweaks setpoint or control mode.
    """
    target_setpoint_f: Optional[float] = None
    control_mode: Optional[Literal["AUTO", "MANUAL", "THERMOSTAT"]] = None


class ZoneCommandRequest(BaseModel):
    """
    Manual override commands exposed as buttons in the UI.
    """
    command: Literal["FORCE_ON", "FORCE_OFF", "AUTO", "THERMOSTAT"]


class ZoneEventPayload(BaseModel):
    """
    Structure used by the collector script when reporting zone activity.
    """
    event: Literal["ON", "OFF", "SAMPLE"]
    zone_room_temp_f: Optional[float] = None
    pipe_temp_f: Optional[float] = None
    outside_temp_f: Optional[float] = None


class BoilerEventPayload(BaseModel):
    """
    Same as ZoneEventPayload but without the extra temps.
    """
    event: Literal["ON", "OFF", "SAMPLE"]
    outside_temp_f: Optional[float] = None


class EventLogModel(BaseModel):
    """
    API representation of the EventLog rows (used in the dashboard timeline).
    """
    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(..., alias="Id")
    timestamp: str = Field(..., alias="Timestamp")
    source: str = Field(..., alias="Source")
    event: Literal["ON", "OFF", "SAMPLE"] = Field(..., alias="Event")
    room_name: Optional[str] = Field(None, alias="RoomName")
    zone_room_temp_f: Optional[float] = Field(None, alias="ZoneRoomTemp_F")
    pipe_temp_f: Optional[float] = Field(None, alias="PipeTemp_F")
    outside_temp_f: Optional[float] = Field(None, alias="OutsideTemp_F")
    duration_seconds: Optional[float] = Field(None, alias="DurationSeconds")
    event_date: Optional[str] = Field(None, alias="EventDate")
    event_time: Optional[str] = Field(None, alias="EventTime")


class TemperatureSampleModel(BaseModel):
    """
    Stored minute-level snapshot of zone temperatures.
    """

    id: int = Field(..., alias="Id")
    timestamp: str = Field(..., alias="Timestamp")
    zone_name: str = Field(..., alias="ZoneName")
    room_temp_f: Optional[float] = Field(None, alias="RoomTemp_F")
    pipe_temp_f: Optional[float] = Field(None, alias="PipeTemp_F")
    outside_temp_f: Optional[float] = Field(None, alias="OutsideTemp_F")


class ZoneScheduleEntryModel(BaseModel):
    """Represents a single scheduled setpoint window for a zone."""

    id: int = Field(..., alias="Id")
    day_of_week: int = Field(..., alias="DayOfWeek")
    start_time: str = Field(..., alias="StartTime")
    end_time: str = Field(..., alias="EndTime")
    setpoint_f: float = Field(..., alias="Setpoint_F")
    enabled: bool = Field(..., alias="Enabled")


class ZoneScheduleEntryInput(BaseModel):
    """Payload entry used when updating zone schedules."""

    day_of_week: int
    start_time: str
    end_time: str
    setpoint_f: float
    enabled: bool = True


class ZoneScheduleUpdateRequest(BaseModel):
    """Request body for replacing a zone's schedule."""

    entries: List[ZoneScheduleEntryInput]


class ZoneScheduleCloneRequest(BaseModel):
    """Payload used to copy a zone schedule to other zones."""

    target_zones: List[str]


class GlobalScheduleUpdateRequest(BaseModel):
    """Request body for replacing the global default schedule."""

    entries: List[ZoneScheduleEntryInput]


class SchedulePresetSummaryModel(BaseModel):
    """Summary of a saved schedule preset."""

    id: int = Field(..., alias="Id")
    name: str = Field(..., alias="Name")
    description: Optional[str] = Field(None, alias="Description")
    created_at: str = Field(..., alias="CreatedAt")
    updated_at: str = Field(..., alias="UpdatedAt")


class SchedulePresetDetailModel(SchedulePresetSummaryModel):
    """Detailed preset information including entries."""

    entries: List[ZoneScheduleEntryModel] = Field(..., alias="Entries")


class SchedulePresetCreateRequest(BaseModel):
    """Create a new preset with a given name and schedule."""

    name: str
    description: Optional[str] = None
    entries: List[ZoneScheduleEntryInput]


class SchedulePresetUpdateRequest(BaseModel):
    """Update preset metadata or entries."""

    name: Optional[str] = None
    description: Optional[str] = None
    entries: Optional[List[ZoneScheduleEntryInput]] = None


class ZoneHistoryBatchRequest(BaseModel):
    """Request payload for fetching multiple zone histories at once."""

    zones: List[str]


class ZoneHistoryBatchResponse(BaseModel):
    """Response wrapper mapping zone names to their histories."""

    histories: Dict[str, List[EventLogModel]]
