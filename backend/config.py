"""
Runtime configuration for the Boiler Controller backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List
import json
import os


# Default number of heating zones. Can be overridden via env variable.
DEFAULT_ZONE_COUNT = 14


def default_zone_names() -> List[str]:
    return [f"Z{i}" for i in range(1, DEFAULT_ZONE_COUNT + 1)]


@dataclass
class Settings:
    """
    Simple settings object populated from environment variables.
    """

    # Database configuration
    # If DATABASE_URL is set (e.g., postgresql://user:pass@host:5432/dbname), use PostgreSQL
    # Otherwise, fall back to SQLite using BOILER_DB_PATH
    database_url: str = os.getenv("DATABASE_URL", "")
    database_path: Path = Path(
        os.getenv("BOILER_DB_PATH", "data/boiler_controller.sqlite3")
    )
    database_type: str = ""  # Will be set in __post_init__: "postgresql" or "sqlite"

    hardware_mode: str = os.getenv("BOILER_HARDWARE_MODE", "mock")
    outdoor_sensor_name: str = os.getenv("BOILER_OUTDOOR_SENSOR", "outdoor")
    zone_names: List[str] = field(
        default_factory=lambda: os.getenv("BOILER_ZONE_NAMES", "")
    )
    zone_config_path: Path = Path(
        os.getenv("BOILER_ZONE_CONFIG", "config/zones.json")
    )
    zone_room_map: Dict[str, str] = field(default_factory=dict)
    time_zone: str = os.getenv("BOILER_TIME_ZONE", "America/Denver")

    def __post_init__(self) -> None:
        # Resolve paths relative to repo root (parent of backend package)
        repo_root = Path(__file__).parent.parent

        # Determine database type
        if self.database_url and self.database_url.startswith(("postgresql://", "postgres://")):
            self.database_type = "postgresql"
        else:
            self.database_type = "sqlite"

        # Make database_path absolute if it's relative (for SQLite)
        if not self.database_path.is_absolute():
            self.database_path = repo_root / self.database_path

        # Make zone_config_path absolute if it's relative
        if not self.zone_config_path.is_absolute():
            self.zone_config_path = repo_root / self.zone_config_path

        if not self.zone_names:
            # BOILER_ZONE_NAMES not provided, fall back to Z1..Z14
            self.zone_names = default_zone_names()
        else:
            self.zone_names = [
                name.strip()
                for name in self.zone_names.split(",")
                if name.strip()
            ]

        # Lazily create the directory that will hold our SQLite file (if using SQLite)
        if self.database_type == "sqlite" and not self.database_path.parent.exists():
            # Creates ./data/ if we are using the default path
            self.database_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.zone_config_path.parent.exists():
            self.zone_config_path.parent.mkdir(parents=True, exist_ok=True)

        self.zone_room_map = self._load_zone_rooms()

    def _load_zone_rooms(self) -> Dict[str, str]:
        """
        Load zone-to-room mapping from JSON file. If the file is missing,
        synthesize a default mapping (Z1 -> Zone 1, etc.) and write it.
        """
        mapping: Dict[str, str] = {}
        if self.zone_config_path.exists():
            try:
                with self.zone_config_path.open("r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                    if isinstance(raw, dict):
                        mapping = {k: str(v) for k, v in raw.items()}
            except (json.JSONDecodeError, OSError):
                mapping = {}

        if not mapping:
            mapping = {zone: f"Zone {zone[1:]}" for zone in self.zone_names}
            mapping["Boiler"] = "Boiler"
            try:
                with self.zone_config_path.open("w", encoding="utf-8") as fh:
                    json.dump(mapping, fh, indent=2)
            except OSError:
                pass

        mapping.setdefault("Boiler", "Boiler")
        return mapping


# Single global settings object imported by other modules.
settings = Settings()
