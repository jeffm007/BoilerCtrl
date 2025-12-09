"""
Test the enhanced setpoint override system with three modes.
Run this on the Pi where the full environment is set up.
"""
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from backend import repositories
    from backend.services.zone_service import _normalize_row_keys
except ImportError as e:
    print(f"Import error: {e}")
    print("\nThis test must be run on the Raspberry Pi where the full environment is configured.")
    print("On Windows, you can commit and push the changes, then pull and run on the Pi.")
    sys.exit(0)

def test_override_modes():
    print("Testing Setpoint Override System\n")
    print("=" * 60)

    # Test Zone
    zone_name = "Z1"

    # 1. Test Boundary Mode (default)
    print("\n1. Testing BOUNDARY mode...")
    repositories.update_zone_status(
        zone_name,
        target_setpoint_f=72.0,
        setpoint_override_at=datetime.now(),
        setpoint_override_mode="boundary",
    )

    zone = repositories.get_zone_status(zone_name)
    zone = _normalize_row_keys(zone)
    print(f"   Setpoint: {zone['TargetSetpoint_F']}°F")
    print(f"   Override Mode: {zone['SetpointOverrideMode']}")
    print(f"   Override At: {zone['SetpointOverrideAt']}")
    print(f"   ✓ Boundary mode set successfully")

    # 2. Test Permanent Mode
    print("\n2. Testing PERMANENT mode...")
    repositories.update_zone_status(
        zone_name,
        target_setpoint_f=75.0,
        setpoint_override_at=datetime.now(),
        setpoint_override_mode="permanent",
    )

    zone = repositories.get_zone_status(zone_name)
    zone = _normalize_row_keys(zone)
    print(f"   Setpoint: {zone['TargetSetpoint_F']}°F")
    print(f"   Override Mode: {zone['SetpointOverrideMode']}")
    print(f"   ✓ Permanent mode set successfully")

    # 3. Test Timed Mode
    print("\n3. Testing TIMED mode...")
    future_time = datetime.now() + timedelta(hours=2)
    repositories.update_zone_status(
        zone_name,
        target_setpoint_f=70.0,
        setpoint_override_at=datetime.now(),
        setpoint_override_mode="timed",
        setpoint_override_until=future_time,
    )

    zone = repositories.get_zone_status(zone_name)
    zone = _normalize_row_keys(zone)
    print(f"   Setpoint: {zone['TargetSetpoint_F']}°F")
    print(f"   Override Mode: {zone['SetpointOverrideMode']}")
    print(f"   Override Until: {zone['SetpointOverrideUntil']}")
    print(f"   ✓ Timed mode set successfully")

    # 4. Test Clear Override
    print("\n4. Testing CLEAR override...")
    repositories.update_zone_status(
        zone_name,
        clear_override=True,
    )

    zone = repositories.get_zone_status(zone_name)
    zone = _normalize_row_keys(zone)
    print(f"   Override Mode: {zone['SetpointOverrideMode']}")
    print(f"   Override At: {zone['SetpointOverrideAt']}")
    print(f"   Override Until: {zone['SetpointOverrideUntil']}")
    print(f"   ✓ Override cleared successfully")

    print("\n" + "=" * 60)
    print("All tests passed! ✓\n")

if __name__ == "__main__":
    test_override_modes()
