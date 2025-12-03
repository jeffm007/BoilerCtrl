"""
Data access layer for SQLite.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence
import sqlite3

from .database import get_connection


def list_zone_status() -> List[Dict[str, Any]]:
    """
    Return current status rows for the 14 heating zones (Boiler excluded).
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM ZoneStatus
            WHERE ZoneName != 'Boiler'
            ORDER BY CAST(SUBSTR(ZoneName, 2) AS INTEGER)
            """
        ).fetchall()
    return rows


def get_zone_status(zone_name: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a single zone row by its identifier (e.g., 'Z3' or 'Boiler').
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM ZoneStatus WHERE ZoneName = ?;", (zone_name,)
        ).fetchone()
    return row


def update_zone_status(
    zone_name: str,
    *,
    current_state: Optional[str] = None,
    zone_room_temp_f: Optional[float] = None,
    pipe_temp_f: Optional[float] = None,
    target_setpoint_f: Optional[float] = None,
    control_mode: Optional[str] = None,
    updated_at: Optional[datetime] = None,
) -> None:
    # We build the SQL statement dynamically so that only provided fields are updated.
    assignments: List[str] = []
    params: List[Any] = []

    if current_state is not None:
        assignments.append("CurrentState = ?")
        params.append(current_state)
    if zone_room_temp_f is not None:
        assignments.append("ZoneRoomTemp_F = ?")
        params.append(zone_room_temp_f)
    if pipe_temp_f is not None:
        assignments.append("PipeTemp_F = ?")
        params.append(pipe_temp_f)
    if target_setpoint_f is not None:
        assignments.append("TargetSetpoint_F = ?")
        params.append(target_setpoint_f)
    if control_mode is not None:
        assignments.append("ControlMode = ?")
        params.append(control_mode)

    if not assignments:
        # Nothing to update; exit early instead of sending an empty UPDATE statement.
        return

    if updated_at is None:
        assignments.append("UpdatedAt = CURRENT_TIMESTAMP")
    else:
        assignments.append("UpdatedAt = ?")
        params.append(updated_at.isoformat())

    params.append(zone_name)

    with get_connection() as conn:
        conn.execute(
            f"UPDATE ZoneStatus SET {', '.join(assignments)} WHERE ZoneName = ?;",
            params,
        )
        conn.commit()


def list_all_zone_rows() -> List[Dict[str, Any]]:
    """
    Fetch status for every zone, including the boiler row.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM ZoneStatus
            ORDER BY CASE
                WHEN ZoneName = 'Boiler' THEN 9999
                ELSE CAST(SUBSTR(ZoneName, 2) AS INTEGER)
            END
            """
        ).fetchall()
    return rows


def get_system_status() -> Dict[str, Any]:
    """
    Return the single SystemStatus row with outdoor temperature metadata.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT OutsideTemp_F, UpdatedAt FROM SystemStatus WHERE Id = 1;"
        ).fetchone()
    return row


def update_system_status(
    outside_temp_f: Optional[float] = None, updated_at: Optional[datetime] = None
) -> None:
    assignments: List[str] = []
    params: List[Any] = []

    if outside_temp_f is not None:
        assignments.append("OutsideTemp_F = ?")
        params.append(outside_temp_f)

    if updated_at is None:
        assignments.append("UpdatedAt = CURRENT_TIMESTAMP")
    else:
        assignments.append("UpdatedAt = ?")
        params.append(updated_at.isoformat())

    if not assignments:
        return

    with get_connection() as conn:
        conn.execute(
            f"UPDATE SystemStatus SET {', '.join(assignments)} WHERE Id = 1;", params
        )
        conn.commit()


def record_event(
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
    Insert an ON/OFF transition into EventLog. The temperatures are optional
    because boiler events do not include room or pipe readings. Duration is
    only populated when we log the OFF event for a zone cycle.
    """
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO EventLog (
                Timestamp,
                Source,
                Event,
                ZoneRoomTemp_F,
                PipeTemp_F,
                OutsideTemp_F,
                DurationSeconds
            )
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                (timestamp or datetime.utcnow()).isoformat(),
                source,
                event,
                zone_room_temp_f,
                pipe_temp_f,
                outside_temp_f,
                duration_seconds,
            ),
        )
        conn.commit()


def record_temperature_sample(
    *,
    zone_name: str,
    room_temp_f: Optional[float],
    pipe_temp_f: Optional[float],
    outside_temp_f: Optional[float],
    timestamp: Optional[datetime] = None,
) -> None:
    """
    Persist a periodic temperature snapshot for later analytics.
    """
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO TemperatureSamples (
                Timestamp,
                ZoneName,
                RoomTemp_F,
                PipeTemp_F,
                OutsideTemp_F
            )
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                (timestamp or datetime.utcnow()).isoformat(),
                zone_name,
                room_temp_f,
                pipe_temp_f,
                outside_temp_f,
            ),
        )
        conn.commit()


def fetch_events(
    *,
    source: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 500,
    exclude_events: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Query the event log with optional filters (source, date range, max rows).
    """
    clauses: List[str] = []
    params: List[Any] = []

    if source:
        clauses.append("Source = ?")
        params.append(source)
    if since:
        clauses.append("Timestamp >= ?")
        params.append(since)
    if until:
        clauses.append("Timestamp <= ?")
        params.append(until)

    # Combine optional filters into a single WHERE clause.
    if exclude_events:
        placeholders = ",".join("?" for _ in exclude_events)
        clauses.append(f"Event NOT IN ({placeholders})")
        params.extend(exclude_events)

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    query = f"""
        SELECT *
        FROM EventLog
        {where_clause}
        ORDER BY Timestamp DESC
        LIMIT ?
    """
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return rows


def list_zone_schedule(zone_name: str) -> List[Dict[str, Any]]:
    """
    Return schedule entries for a zone ordered by day/time.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                Id,
                ZoneName,
                DayOfWeek,
                StartTime,
                EndTime,
                Setpoint_F,
                Enabled,
                CreatedAt,
                UpdatedAt
            FROM ZoneSchedules
            WHERE ZoneName = ?
            ORDER BY DayOfWeek ASC, StartTime ASC;
            """,
            (zone_name,),
        ).fetchall()
    return rows


def replace_zone_schedule(
    zone_name: str, entries: Sequence[Dict[str, Any]]
) -> None:
    """
    Replace the stored schedule for a zone with the provided entries.
    """
    normalized_entries = [
        {
            "DayOfWeek": entry["DayOfWeek"],
            "StartTime": entry["StartTime"],
            "EndTime": entry["EndTime"],
            "Setpoint_F": entry["Setpoint_F"],
            "Enabled": 1 if entry.get("Enabled", True) else 0,
        }
        for entry in entries
    ]

    with get_connection() as conn:
        conn.execute("DELETE FROM ZoneSchedules WHERE ZoneName = ?;", (zone_name,))
        if normalized_entries:
            conn.executemany(
                """
                INSERT INTO ZoneSchedules (
                    ZoneName,
                    DayOfWeek,
                    StartTime,
                    EndTime,
                    Setpoint_F,
                    Enabled
                )
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                [
                    (
                        zone_name,
                        entry["DayOfWeek"],
                        entry["StartTime"],
                        entry["EndTime"],
                        entry["Setpoint_F"],
                        entry["Enabled"],
                    )
                    for entry in normalized_entries
                ],
            )
        conn.commit()


def list_all_schedules() -> List[Dict[str, Any]]:
    """
    Fetch schedule entries for every zone (used for previews).
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                Id,
                ZoneName,
                DayOfWeek,
                StartTime,
                EndTime,
                Setpoint_F,
                Enabled,
                CreatedAt,
                UpdatedAt
            FROM ZoneSchedules
            ORDER BY ZoneName ASC, DayOfWeek ASC, StartTime ASC;
            """
        ).fetchall()
    return rows


def list_global_schedule() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                Id,
                DayOfWeek,
                StartTime,
                EndTime,
                Setpoint_F,
                Enabled,
                CreatedAt,
                UpdatedAt
            FROM GlobalSchedule
            ORDER BY DayOfWeek ASC, StartTime ASC;
            """
        ).fetchall()
    return rows


def replace_global_schedule(entries: Sequence[Dict[str, Any]]) -> None:
    normalized_entries = [
        {
            "DayOfWeek": entry["DayOfWeek"],
            "StartTime": entry["StartTime"],
            "EndTime": entry["EndTime"],
            "Setpoint_F": entry["Setpoint_F"],
            "Enabled": 1 if entry.get("Enabled", True) else 0,
        }
        for entry in entries
    ]

    with get_connection() as conn:
        conn.execute("DELETE FROM GlobalSchedule;")
        if normalized_entries:
            conn.executemany(
                """
                INSERT INTO GlobalSchedule (
                    DayOfWeek,
                    StartTime,
                    EndTime,
                    Setpoint_F,
                    Enabled
                )
                VALUES (?, ?, ?, ?, ?);
                """,
                [
                    (
                        entry["DayOfWeek"],
                        entry["StartTime"],
                        entry["EndTime"],
                        entry["Setpoint_F"],
                        entry["Enabled"],
                    )
                    for entry in normalized_entries
                ],
            )
        conn.commit()


def list_presets() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT Id, Name, Description, CreatedAt, UpdatedAt
            FROM SchedulePresets
            ORDER BY Name COLLATE NOCASE ASC;
            """
        ).fetchall()
    return rows


def get_preset_with_entries(preset_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        preset = conn.execute(
            """
            SELECT Id, Name, Description, CreatedAt, UpdatedAt
            FROM SchedulePresets
            WHERE Id = ?;
            """,
            (preset_id,),
        ).fetchone()
        if not preset:
            return None
        entries = conn.execute(
            """
            SELECT
                Id,
                DayOfWeek,
                StartTime,
                EndTime,
                Setpoint_F,
                Enabled,
                CreatedAt,
                UpdatedAt
            FROM SchedulePresetEntries
            WHERE PresetId = ?
            ORDER BY DayOfWeek ASC, StartTime ASC;
            """,
            (preset_id,),
        ).fetchall()
    preset["Entries"] = entries
    return preset


def create_preset(
    *,
    name: str,
    description: Optional[str],
    entries: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    normalized_entries = [
        {
            "DayOfWeek": entry["DayOfWeek"],
            "StartTime": entry["StartTime"],
            "EndTime": entry["EndTime"],
            "Setpoint_F": entry["Setpoint_F"],
            "Enabled": 1 if entry.get("Enabled", True) else 0,
        }
        for entry in entries
    ]

    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO SchedulePresets (Name, Description) VALUES (?, ?);",
                (name, description),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("A preset with that name already exists") from exc

        preset_id = cursor.lastrowid
        if normalized_entries:
            conn.executemany(
                """
                INSERT INTO SchedulePresetEntries (
                    PresetId,
                    DayOfWeek,
                    StartTime,
                    EndTime,
                    Setpoint_F,
                    Enabled
                )
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                [
                    (
                        preset_id,
                        entry["DayOfWeek"],
                        entry["StartTime"],
                        entry["EndTime"],
                        entry["Setpoint_F"],
                        entry["Enabled"],
                    )
                    for entry in normalized_entries
                ],
            )
        conn.commit()

    preset = get_preset_with_entries(preset_id)
    if not preset:
        raise RuntimeError("Failed to fetch newly created preset")
    return preset


def update_preset_metadata(
    preset_id: int,
    *,
    name: Optional[str],
    description: Optional[str],
) -> None:
    assignments: List[str] = []
    params: List[Any] = []
    if name is not None:
        assignments.append("Name = ?")
        params.append(name)
    if description is not None:
        assignments.append("Description = ?")
        params.append(description)
    if not assignments:
        return
    assignments.append("UpdatedAt = CURRENT_TIMESTAMP")
    params.append(preset_id)
    with get_connection() as conn:
        try:
            conn.execute(
                f"UPDATE SchedulePresets SET {', '.join(assignments)} WHERE Id = ?;",
                params,
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("A preset with that name already exists") from exc


def replace_preset_entries(
    preset_id: int, entries: Sequence[Dict[str, Any]]
) -> None:
    normalized_entries = [
        {
            "DayOfWeek": entry["DayOfWeek"],
            "StartTime": entry["StartTime"],
            "EndTime": entry["EndTime"],
            "Setpoint_F": entry["Setpoint_F"],
            "Enabled": 1 if entry.get("Enabled", True) else 0,
        }
        for entry in entries
    ]

    with get_connection() as conn:
        conn.execute("DELETE FROM SchedulePresetEntries WHERE PresetId = ?;", (preset_id,))
        if normalized_entries:
            conn.executemany(
                """
                INSERT INTO SchedulePresetEntries (
                    PresetId,
                    DayOfWeek,
                    StartTime,
                    EndTime,
                    Setpoint_F,
                    Enabled
                )
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                [
                    (
                        preset_id,
                        entry["DayOfWeek"],
                        entry["StartTime"],
                        entry["EndTime"],
                        entry["Setpoint_F"],
                        entry["Enabled"],
                    )
                    for entry in normalized_entries
                ],
            )
        conn.execute(
            "UPDATE SchedulePresets SET UpdatedAt = CURRENT_TIMESTAMP WHERE Id = ?;",
            (preset_id,),
        )
        conn.commit()


def delete_preset(preset_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM SchedulePresets WHERE Id = ?;", (preset_id,))
        conn.commit()
