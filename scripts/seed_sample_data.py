"""
Populate the SQLite database with sample boiler data.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from random import Random

from backend.config import settings
from backend.database import init_db
from backend import repositories


def seed_zone_status(randomizer: Random) -> None:
    """
    Populate ZoneStatus with plausible values so the dashboard has data.
    """
    now = datetime.utcnow()

    for index, zone_name in enumerate(settings.zone_names, start=1):
        # Cycle every third zone to "ON" to create variety in the UI.
        is_on = index % 3 == 1
        zone_room_temp = 67.0 + index * 0.4 + randomizer.uniform(-0.5, 0.5)
        pipe_temp = (
            118.0 + index * 1.2 + randomizer.uniform(-1.5, 1.5)
            if is_on
            else 95.0 + index * 0.9 + randomizer.uniform(-1.0, 1.0)
        )
        target_setpoint = 69.0 + (index % 4) * 0.5
        updated_at = now - timedelta(minutes=randomizer.randint(1, 90))

        repositories.update_zone_status(
            zone_name,
            current_state="ON" if is_on else "OFF",
            zone_room_temp_f=round(zone_room_temp, 1),
            pipe_temp_f=round(pipe_temp, 1),
            target_setpoint_f=round(target_setpoint, 1),
            control_mode="AUTO",
            updated_at=updated_at,
        )

    # Boiler row
    repositories.update_zone_status(
        "Boiler",
        current_state="ON",
        control_mode="AUTO",
    )

    repositories.update_system_status(
        outside_temp_f=28.5 + randomizer.uniform(-2.5, 2.5),
        updated_at=now,
    )


def seed_event_log(randomizer: Random) -> None:
    """
    Generate synthetic ON/OFF cycles for each zone and the boiler.
    """
    repositories.fetch_events(limit=1)  # ensure connection works

    now = datetime.utcnow()
    base_start = now - timedelta(hours=12)

    for index, zone_name in enumerate(settings.zone_names, start=1):
        start_time = base_start + timedelta(minutes=index * 12)
        # Each zone performs three heating cycles spaced two hours apart.
        for cycle in range(3):
            on_time = start_time + timedelta(hours=cycle * 2)
            off_time = on_time + timedelta(minutes=25 + randomizer.randint(-5, 5))

            room_temp = 66.5 + index * 0.35 + cycle * 0.2 + randomizer.uniform(-0.6, 0.6)
            pipe_temp_on = 120.0 + index * 1.1 + cycle * 2.0 + randomizer.uniform(-2.5, 2.5)
            pipe_temp_off = pipe_temp_on - randomizer.uniform(8.0, 12.0)
            outside_temp = 30.0 - cycle * 0.6 + randomizer.uniform(-1.0, 1.0)

            repositories.record_event(
                source=zone_name,
                event="ON",
                zone_room_temp_f=round(room_temp, 1),
                pipe_temp_f=round(pipe_temp_on, 1),
                outside_temp_f=round(outside_temp, 1),
                duration_seconds=None,
                timestamp=on_time,
            )
            repositories.record_event(
                source=zone_name,
                event="OFF",
                zone_room_temp_f=round(room_temp + 1.5, 1),
                pipe_temp_f=round(pipe_temp_off, 1),
                outside_temp_f=round(outside_temp, 1),
                duration_seconds=(off_time - on_time).total_seconds(),
                timestamp=off_time,
            )

    # Boiler cycles aligned with zones
    for cycle in range(6):
        on_time = base_start + timedelta(hours=cycle * 2)
        off_time = on_time + timedelta(minutes=32 + randomizer.randint(-4, 6))
        outside_temp = 30.0 - cycle * 0.7 + randomizer.uniform(-1.5, 1.5)

        repositories.record_event(
            source="Boiler",
            event="ON",
            zone_room_temp_f=None,
            pipe_temp_f=None,
            outside_temp_f=round(outside_temp, 1),
            duration_seconds=None,
            timestamp=on_time,
        )
        repositories.record_event(
            source="Boiler",
            event="OFF",
            zone_room_temp_f=None,
            pipe_temp_f=None,
            outside_temp_f=round(outside_temp, 1),
            duration_seconds=(off_time - on_time).total_seconds(),
            timestamp=off_time,
        )


def main() -> None:
    # Deterministic seed so repeated runs produce the same data (handy for UI testing).
    randomizer = Random(42)
    init_db()

    seed_zone_status(randomizer)
    seed_event_log(randomizer)
    print("Sample data inserted.")


if __name__ == "__main__":
    main()
