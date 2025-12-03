from datetime import datetime

from backend.config import settings
from backend.services.zone_service import ZoneService
from backend.services.event_service import EventService
from backend.hardware.controller import MockHardwareController
from backend.database import init_db
from backend import repositories


def setup_module(module):
    init_db()


def test_sync_auto_setpoint_updates_target():
    hw = MockHardwareController(settings.zone_names)
    svc = ZoneService(hardware=hw, event_service=EventService())

    # Prepare a simple schedule for Z1
    repositories.replace_zone_schedule(
        "Z1",
        [
            {
                "DayOfWeek": datetime.now().weekday(),
                "StartTime": "00:00",
                "EndTime": "23:59",
                "Setpoint_F": 70.0,
                "Enabled": 1,
            }
        ],
    )

    row = repositories.get_zone_status("Z1")
    assert row is not None
    row["ControlMode"] = "AUTO"
    updated = svc._sync_auto_setpoint(row)
    assert round(updated.get("TargetSetpoint_F") or 0, 1) == 70.0
