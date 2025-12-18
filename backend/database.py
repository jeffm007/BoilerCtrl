"""
Database helpers and schema initialization for SQLite.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Generator, Iterable, Tuple
import sqlite3

from .config import settings


def dict_factory(cursor: sqlite3.Cursor, row: Tuple[Any, ...]) -> Dict[str, Any]:
    """
    Convert sqlite rows into dictionaries keyed by column name.
    """
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager that yields a SQLite database connection and guarantees it is closed.
    """
    conn = sqlite3.connect(settings.database_path, timeout=5.0)
    conn.row_factory = dict_factory
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        conn.close()


def _get_schema_statements() -> Iterable[str]:
    """
    Returns SQLite schema SQL statements.
    """
    return _SQLITE_SCHEMA_STATEMENTS


# SQLite schema
_SQLITE_SCHEMA_STATEMENTS: Iterable[str] = (
    """
    CREATE TABLE IF NOT EXISTS ZoneStatus (
        ZoneName TEXT PRIMARY KEY,
        CurrentState TEXT NOT NULL CHECK (CurrentState IN ('ON', 'OFF')),
        ZoneRoomTemp_F REAL,
        PipeTemp_F REAL,
        TargetSetpoint_F REAL,
        ControlMode TEXT NOT NULL CHECK (ControlMode IN ('AUTO', 'MANUAL', 'THERMOSTAT')),
        SetpointOverrideAt TEXT,
        SetpointOverrideMode TEXT CHECK (SetpointOverrideMode IN ('boundary', 'permanent', 'timed')),
        SetpointOverrideUntil TEXT,
        UpdatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS SystemStatus (
        Id INTEGER PRIMARY KEY CHECK (Id = 1),
        OutsideTemp_F REAL,
        UpdatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS EventLog (
        Id INTEGER PRIMARY KEY AUTOINCREMENT,
        Timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        Source TEXT NOT NULL,
        Event TEXT NOT NULL,
        ZoneRoomTemp_F REAL,
        PipeTemp_F REAL,
        OutsideTemp_F REAL,
        DurationSeconds REAL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_eventlog_source_time ON EventLog (Source, Timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_eventlog_time ON EventLog (Timestamp DESC);",
    """
    CREATE TABLE IF NOT EXISTS TemperatureSamples (
        Id INTEGER PRIMARY KEY AUTOINCREMENT,
        Timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ZoneName TEXT NOT NULL,
        RoomTemp_F REAL,
        PipeTemp_F REAL,
        OutsideTemp_F REAL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_samples_zone_time ON TemperatureSamples (ZoneName, Timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_samples_time ON TemperatureSamples (Timestamp DESC);",
    """
    CREATE TABLE IF NOT EXISTS ZoneSchedules (
        Id INTEGER PRIMARY KEY AUTOINCREMENT,
        ZoneName TEXT NOT NULL,
        DayOfWeek INTEGER NOT NULL CHECK (DayOfWeek BETWEEN 0 AND 6),
        StartTime TEXT NOT NULL,
        EndTime TEXT NOT NULL,
        Setpoint_F REAL NOT NULL,
        Enabled INTEGER NOT NULL DEFAULT 1,
        CreatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UpdatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (ZoneName, DayOfWeek, StartTime)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_schedules_zone_day ON ZoneSchedules (ZoneName, DayOfWeek, StartTime);",
    """
    CREATE TABLE IF NOT EXISTS GlobalSchedule (
        Id INTEGER PRIMARY KEY AUTOINCREMENT,
        DayOfWeek INTEGER NOT NULL CHECK (DayOfWeek BETWEEN 0 AND 6),
        StartTime TEXT NOT NULL,
        EndTime TEXT NOT NULL,
        Setpoint_F REAL NOT NULL,
        Enabled INTEGER NOT NULL DEFAULT 1,
        CreatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UpdatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (DayOfWeek, StartTime)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_global_schedule ON GlobalSchedule (DayOfWeek, StartTime);",
    """
    CREATE TABLE IF NOT EXISTS SchedulePresets (
        Id INTEGER PRIMARY KEY AUTOINCREMENT,
        Name TEXT NOT NULL UNIQUE,
        Description TEXT,
        CreatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UpdatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS SchedulePresetEntries (
        Id INTEGER PRIMARY KEY AUTOINCREMENT,
        PresetId INTEGER NOT NULL,
        DayOfWeek INTEGER NOT NULL CHECK (DayOfWeek BETWEEN 0 AND 6),
        StartTime TEXT NOT NULL,
        EndTime TEXT NOT NULL,
        Setpoint_F REAL NOT NULL,
        Enabled INTEGER NOT NULL DEFAULT 1,
        CreatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UpdatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (PresetId, DayOfWeek, StartTime),
        FOREIGN KEY (PresetId) REFERENCES SchedulePresets(Id) ON DELETE CASCADE
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_preset_entries ON SchedulePresetEntries (PresetId, DayOfWeek, StartTime);",
)


def _ensure_zone_status_control_mode(conn: sqlite3.Connection) -> None:
    """Upgrade ZoneStatus table to allow the THERMOSTAT control mode."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='ZoneStatus';"
    ).fetchone()
    if not row:
        return
    create_sql = row["sql"] if isinstance(row, dict) else row[0]
    if create_sql and "THERMOSTAT" in create_sql:
        return

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ZoneStatus_new (
            ZoneName TEXT PRIMARY KEY,
            CurrentState TEXT NOT NULL CHECK (CurrentState IN ('ON', 'OFF')),
            ZoneRoomTemp_F REAL,
            PipeTemp_F REAL,
            TargetSetpoint_F REAL,
            ControlMode TEXT NOT NULL CHECK (ControlMode IN ('AUTO', 'MANUAL', 'THERMOSTAT')),
            UpdatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.execute(
        """
        INSERT INTO ZoneStatus_new (
            ZoneName, CurrentState, ZoneRoomTemp_F, PipeTemp_F, TargetSetpoint_F, ControlMode
        )
        SELECT ZoneName, CurrentState, ZoneRoomTemp_F, PipeTemp_F, TargetSetpoint_F, ControlMode
        FROM ZoneStatus;
        """
    )
    conn.execute("DROP TABLE ZoneStatus;")
    conn.execute("ALTER TABLE ZoneStatus_new RENAME TO ZoneStatus;")


def _ensure_duration_seconds_column(conn: sqlite3.Connection) -> None:
    """Add DurationSeconds column to EventLog if it doesn't exist."""
    try:
        conn.execute("ALTER TABLE EventLog ADD COLUMN DurationSeconds REAL;")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def _ensure_setpoint_override_column(conn: sqlite3.Connection) -> None:
    """Add SetpointOverrideAt column to ZoneStatus if it doesn't exist."""
    try:
        conn.execute("ALTER TABLE ZoneStatus ADD COLUMN SetpointOverrideAt TEXT;")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def _ensure_override_mode_column(conn: sqlite3.Connection) -> None:
    """Add SetpointOverrideMode column to ZoneStatus if it doesn't exist."""
    try:
        conn.execute("ALTER TABLE ZoneStatus ADD COLUMN SetpointOverrideMode TEXT;")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def _ensure_override_until_column(conn: sqlite3.Connection) -> None:
    """Add SetpointOverrideUntil column to ZoneStatus if it doesn't exist."""
    try:
        conn.execute("ALTER TABLE ZoneStatus ADD COLUMN SetpointOverrideUntil TEXT;")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def _ensure_override_scheduled_value_column(conn: sqlite3.Connection) -> None:
    """Add SetpointOverrideScheduledValue column to ZoneStatus if it doesn't exist."""
    try:
        conn.execute("ALTER TABLE ZoneStatus ADD COLUMN SetpointOverrideScheduledValue REAL;")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def bootstrap_zone_rows(conn: sqlite3.Connection) -> None:
    """
    Ensure that each zone (plus the special Boiler row) exists exactly once.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT ZoneName FROM ZoneStatus;")
    existing = cursor.fetchall()
    # Handle both dict-style and tuple results from SQLite
    if existing and isinstance(existing[0], dict):
        existing_names = {row["ZoneName"] for row in existing}
    else:
        existing_names = {row[0] for row in existing}

    rows_to_insert = [
        (
            zone,
            "OFF",
            None,
            None,
            None,
            "AUTO",
        )
        for zone in settings.zone_names
        if zone not in existing_names
    ]

    if rows_to_insert:
        cursor.executemany(
            """
            INSERT INTO ZoneStatus (
                ZoneName,
                CurrentState,
                ZoneRoomTemp_F,
                PipeTemp_F,
                TargetSetpoint_F,
                ControlMode
            )
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            rows_to_insert,
        )

    cursor.execute("SELECT Id FROM SystemStatus WHERE Id = 1;")
    system_row = cursor.fetchone()
    if not system_row:
        # A single row acts as a key/value store for outdoor metrics.
        cursor.execute(
            "INSERT INTO SystemStatus (Id, OutsideTemp_F) VALUES (1, NULL);"
        )

    cursor.close()


def init_db() -> None:
    """
    Create schema (if needed) and populate rows that the application expects.
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        for statement in _get_schema_statements():
            cursor.execute(statement)

        _ensure_zone_status_control_mode(conn)
        _ensure_duration_seconds_column(conn)
        _ensure_setpoint_override_column(conn)
        _ensure_override_mode_column(conn)
        _ensure_override_until_column(conn)
        _ensure_override_scheduled_value_column(conn)

        bootstrap_zone_rows(conn)

        # Finally, commit anything that's pending
        conn.commit()
        cursor.close()


if __name__ == "__main__":
    init_db()
    print(f"SQLite database initialized at {settings.database_path}")
