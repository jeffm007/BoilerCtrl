"""
Service layer for event logging.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple
import logging
import time

from .. import repositories
from ..config import settings
from ..schemas import EventLogModel


def _split_timestamp(value: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not value:
        return None, None
    normalized = value.replace(" ", "T")
    parts = normalized.split("T")
    date_part = parts[0] if parts else None
    time_part = parts[1] if len(parts) > 1 else None
    if time_part:
        time_part = time_part.replace("Z", "")
        if "." in time_part:
            time_part = time_part.split(".")[0]
    return date_part, time_part


class EventService:
    """
    Thin wrapper around repository helpers so our FastAPI endpoints can
    work with strongly-typed Pydantic models.
    """

    def log_event(
        self,
        *,
        source: str,
        event: str,
        zone_room_temp_f: Optional[float],
        pipe_temp_f: Optional[float],
        outside_temp_f: Optional[float],
        duration_seconds: Optional[float],
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Insert a new record into the EventLog table.
        """
        repositories.record_event(
            source=source,
            event=event,
            zone_room_temp_f=zone_room_temp_f,
            pipe_temp_f=pipe_temp_f,
            outside_temp_f=outside_temp_f,
            duration_seconds=duration_seconds,
            timestamp=timestamp,
        )

    def list_events(
        self,
        *,
        source: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 500,
        include_samples: bool = False,
    ) -> List[EventLogModel]:
        """
        Retrieve recent events (optionally filtered) as Pydantic models.
        """
        start_time = time.perf_counter()
        rows = repositories.fetch_events(
            source=source,
            since=since,
            until=until,
            limit=limit,
            exclude_events=None if include_samples else ["SAMPLE"],
        )
        for row in rows:
            row["RoomName"] = settings.zone_room_map.get(
                row.get("Source", ""), row.get("Source")
            )
            date_part, time_part = _split_timestamp(row.get("Timestamp"))
            row["EventDate"] = date_part
            row["EventTime"] = time_part
        duration = time.perf_counter() - start_time
        logging.getLogger(__name__).info(
            "events.list source=%s limit=%s rows=%s duration=%.3fs samples=%s",
            source or "*",
            limit,
            len(rows),
            duration,
            include_samples,
        )
        return [EventLogModel.model_validate(row) for row in rows]
