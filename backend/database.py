"""
Database helpers and schema initialization for both SQLite and PostgreSQL.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Generator, Iterable, Tuple, Union
import sqlite3

from .config import settings

# Import psycopg2 if available (for PostgreSQL)
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def dict_factory(cursor: sqlite3.Cursor, row: Tuple[Any, ...]) -> Dict[str, Any]:
    """
    Convert sqlite rows into dictionaries keyed by column name.
    """
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


@contextmanager
def get_connection() -> Generator[Union[sqlite3.Connection, Any], None, None]:
    """
    Context manager that yields a database connection and guarantees it is closed.
    Returns either SQLite or PostgreSQL connection based on settings.database_type.
    """
    if settings.database_type == "postgresql":
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError("psycopg2 is required for PostgreSQL but not installed")

        conn = psycopg2.connect(
            settings.database_url,
            cursor_factory=psycopg2.extras.RealDictCursor
        )
        try:
            yield conn
        finally:
            conn.close()
    else:
        # SQLite mode
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
    Returns schema SQL statements compatible with the current database type.
    PostgreSQL uses SERIAL instead of AUTOINCREMENT, and different timestamp handling.
    """
    if settings.database_type == "postgresql":
        return _POSTGRES_SCHEMA_STATEMENTS
    else:
        return _SQLITE_SCHEMA_STATEMENTS


# SQLite-specific schema
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


# PostgreSQL-specific schema
_POSTGRES_SCHEMA_STATEMENTS: Iterable[str] = (
    """
    CREATE TABLE IF NOT EXISTS ZoneStatus (
        ZoneName TEXT PRIMARY KEY,
        CurrentState TEXT NOT NULL CHECK (CurrentState IN ('ON', 'OFF')),
        ZoneRoomTemp_F REAL,
        PipeTemp_F REAL,
        TargetSetpoint_F REAL,
        ControlMode TEXT NOT NULL CHECK (ControlMode IN ('AUTO', 'MANUAL', 'THERMOSTAT')),
        SetpointOverrideAt TIMESTAMP,
        SetpointOverrideMode TEXT CHECK (SetpointOverrideMode IN ('boundary', 'permanent', 'timed')),
        SetpointOverrideUntil TIMESTAMP,
        UpdatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS SystemStatus (
        Id INTEGER PRIMARY KEY CHECK (Id = 1),
        OutsideTemp_F REAL,
        UpdatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS EventLog (
        Id SERIAL PRIMARY KEY,
        Timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
        Id SERIAL PRIMARY KEY,
        Timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
        Id SERIAL PRIMARY KEY,
        ZoneName TEXT NOT NULL,
        DayOfWeek INTEGER NOT NULL CHECK (DayOfWeek BETWEEN 0 AND 6),
        StartTime TEXT NOT NULL,
        EndTime TEXT NOT NULL,
        Setpoint_F REAL NOT NULL,
        Enabled INTEGER NOT NULL DEFAULT 1,
        CreatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UpdatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (ZoneName, DayOfWeek, StartTime)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_schedules_zone_day ON ZoneSchedules (ZoneName, DayOfWeek, StartTime);",
    """
    CREATE TABLE IF NOT EXISTS GlobalSchedule (
        Id SERIAL PRIMARY KEY,
        DayOfWeek INTEGER NOT NULL CHECK (DayOfWeek BETWEEN 0 AND 6),
        StartTime TEXT NOT NULL,
        EndTime TEXT NOT NULL,
        Setpoint_F REAL NOT NULL,
        Enabled INTEGER NOT NULL DEFAULT 1,
        CreatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UpdatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (DayOfWeek, StartTime)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_global_schedule ON GlobalSchedule (DayOfWeek, StartTime);",
    """
    CREATE TABLE IF NOT EXISTS SchedulePresets (
        Id SERIAL PRIMARY KEY,
        Name TEXT NOT NULL UNIQUE,
        Description TEXT,
        CreatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UpdatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS SchedulePresetEntries (
        Id SERIAL PRIMARY KEY,
        PresetId INTEGER NOT NULL,
        DayOfWeek INTEGER NOT NULL CHECK (DayOfWeek BETWEEN 0 AND 6),
        StartTime TEXT NOT NULL,
        EndTime TEXT NOT NULL,
        Setpoint_F REAL NOT NULL,
        Enabled INTEGER NOT NULL DEFAULT 1,
        CreatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UpdatedAt TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (PresetId, DayOfWeek, StartTime),
        FOREIGN KEY (PresetId) REFERENCES SchedulePresets(Id) ON DELETE CASCADE
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_preset_entries ON SchedulePresetEntries (PresetId, DayOfWeek, StartTime);",
)


def _ensure_zone_status_control_mode(conn: Union[sqlite3.Connection, Any]) -> None:
    """Upgrade ZoneStatus table to allow the THERMOSTAT control mode (SQLite only)."""
    if settings.database_type != "sqlite":
        return  # PostgreSQL handles this in initial schema

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
            ZoneName,
            CurrentState,
            ZoneRoomTemp_F,
            PipeTemp_F,
            TargetSetpoint_F,
            ControlMode,
            UpdatedAt
        )
        SELECT
            ZoneName,
            CurrentState,
            ZoneRoomTemp_F,
            PipeTemp_F,
            TargetSetpoint_F,
            CASE
                WHEN ControlMode IN ('AUTO', 'MANUAL') THEN ControlMode
                ELSE 'MANUAL'
            END AS ControlMode,
            UpdatedAt
        FROM ZoneStatus;
        """
    )
    conn.execute("DROP TABLE ZoneStatus;")
    conn.execute("ALTER TABLE ZoneStatus_new RENAME TO ZoneStatus;")


def _ensure_duration_seconds_column(conn: Union[sqlite3.Connection, Any]) -> None:
    """Add DurationSeconds column to EventLog if it doesn't exist."""
    if settings.database_type == "postgresql":
        # Use PostgreSQL syntax to add column if not exists
        cursor = conn.cursor()
        cursor.execute("""
            DO $$
            BEGIN
                BEGIN
                    ALTER TABLE EventLog ADD COLUMN DurationSeconds REAL;
                EXCEPTION
                    WHEN duplicate_column THEN NULL;
                END;
            END $$;
        """)
        cursor.close()
    else:
        # SQLite syntax
        try:
            conn.execute("ALTER TABLE EventLog ADD COLUMN DurationSeconds REAL;")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def _ensure_setpoint_override_column(conn: Union[sqlite3.Connection, Any]) -> None:
    """Add SetpointOverrideAt column to ZoneStatus if it doesn't exist."""
    if settings.database_type == "postgresql":
        # Use PostgreSQL syntax to add column if not exists
        cursor = conn.cursor()
        cursor.execute("""
            DO $$
            BEGIN
                BEGIN
                    ALTER TABLE ZoneStatus ADD COLUMN SetpointOverrideAt TIMESTAMP;
                EXCEPTION
                    WHEN duplicate_column THEN NULL;
                END;
            END $$;
        """)
        cursor.close()
    else:
        # SQLite syntax
        try:
            conn.execute("ALTER TABLE ZoneStatus ADD COLUMN SetpointOverrideAt TEXT;")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def _ensure_override_mode_column(conn: Union[sqlite3.Connection, Any]) -> None:
    """Add SetpointOverrideMode column to ZoneStatus if it doesn't exist."""
    if settings.database_type == "postgresql":
        cursor = conn.cursor()
        cursor.execute("""
            DO $$
            BEGIN
                BEGIN
                    ALTER TABLE ZoneStatus ADD COLUMN SetpointOverrideMode TEXT
                    CHECK (SetpointOverrideMode IN ('boundary', 'permanent', 'timed'));
                EXCEPTION
                    WHEN duplicate_column THEN NULL;
                END;
            END $$;
        """)
        cursor.close()
    else:
        # SQLite syntax - note: can't add CHECK constraint via ALTER TABLE
        try:
            conn.execute("ALTER TABLE ZoneStatus ADD COLUMN SetpointOverrideMode TEXT;")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def _ensure_override_until_column(conn: Union[sqlite3.Connection, Any]) -> None:
    """Add SetpointOverrideUntil column to ZoneStatus if it doesn't exist."""
    if settings.database_type == "postgresql":
        cursor = conn.cursor()
        cursor.execute("""
            DO $$
            BEGIN
                BEGIN
                    ALTER TABLE ZoneStatus ADD COLUMN SetpointOverrideUntil TIMESTAMP;
                EXCEPTION
                    WHEN duplicate_column THEN NULL;
                END;
            END $$;
        """)
        cursor.close()
    else:
        # SQLite syntax
        try:
            conn.execute("ALTER TABLE ZoneStatus ADD COLUMN SetpointOverrideUntil TEXT;")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def bootstrap_zone_rows(conn: Union[sqlite3.Connection, Any]) -> None:
    """
    Ensure that each zone (plus the special Boiler row) exists exactly once.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT ZoneName FROM ZoneStatus;")
    existing = cursor.fetchall()
    # Handle both dict-style (RealDictRow/SQLite dict_factory) and tuple results
    # PostgreSQL returns lowercase column names, SQLite preserves case
    if existing and isinstance(existing[0], dict):
        # Try both ZoneName and zonename for compatibility
        if "ZoneName" in existing[0]:
            existing_names = {row["ZoneName"] for row in existing}
        else:
            existing_names = {row["zonename"] for row in existing}
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

    if "Boiler" not in existing_names:
        rows_to_insert.append(("Boiler", "OFF", None, None, None, "AUTO"))

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
            VALUES (%s, %s, %s, %s, %s, %s);
            """ if settings.database_type == "postgresql" else """
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
        if settings.database_type == "postgresql":
            cursor.execute(
                "INSERT INTO SystemStatus (Id, OutsideTemp_F) VALUES (1, NULL);"
            )
        else:
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

        bootstrap_zone_rows(conn)
        conn.commit()
        cursor.close()


if __name__ == "__main__":
    init_db()
    if settings.database_type == "postgresql":
        print(f"PostgreSQL database initialized at {settings.database_url}")
    else:
        print(f"SQLite database initialized at {settings.database_path}")
