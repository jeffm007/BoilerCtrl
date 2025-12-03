from datetime import datetime

from backend.database import init_db
from backend import repositories


def test_event_log_insert_and_fetch(tmp_path, monkeypatch):
    # Point DB to a temp file
    db_path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("BOILER_DB_PATH", str(db_path))
    init_db()

    # Insert a couple events
    now = datetime.utcnow()
    repositories.record_event(
        source="Z1",
        event="ON",
        zone_room_temp_f=68.0,
        pipe_temp_f=120.0,
        outside_temp_f=30.0,
        duration_seconds=None,
        timestamp=now,
    )
    repositories.record_event(
        source="Z1",
        event="OFF",
        zone_room_temp_f=69.0,
        pipe_temp_f=110.0,
        outside_temp_f=30.0,
        duration_seconds=600.0,
        timestamp=now,
    )

    rows = repositories.fetch_events(source="Z1", limit=10)
    assert len(rows) >= 2
    assert {r["Event"] for r in rows} >= {"ON", "OFF"}
