#!/usr/bin/env python
"""
Fix permanent overrides - convert to boundary mode with scheduled value
"""
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import get_connection
from backend.services.zone_service import ZoneService
from backend.hardware.controller import MockHardwareController
from backend.services.event_service import EventService
from backend.config import settings

def main():
    """Convert all permanent overrides to boundary mode with correct scheduled values."""
    
    # Create service to resolve schedules
    hw = MockHardwareController(zones=settings.zone_names)
    event_service = EventService()
    zone_service = ZoneService(hw, event_service)
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Find all zones with permanent overrides
        cursor.execute("""
            SELECT ZoneName, TargetSetpoint_F, SetpointOverrideAt
            FROM ZoneStatus
            WHERE SetpointOverrideMode = 'permanent'
        """)
        
        permanent_overrides = cursor.fetchall()
        
        if not permanent_overrides:
            print("No permanent overrides found.")
            return
        
        print(f"Found {len(permanent_overrides)} zones with permanent overrides:")
        for row in permanent_overrides:
            print(f"  - {row['ZoneName']}: {row['TargetSetpoint_F']}°F (set at {row['SetpointOverrideAt']})")
        
        response = input("\nConvert all to boundary mode? (y/n): ")
        if response.lower() != 'y':
            print("Cancelled.")
            return
        
        # Convert each one
        converted = 0
        for row in permanent_overrides:
            zone_name = row['ZoneName']
            
            # Get the current scheduled setpoint for this zone
            scheduled_setpoint = zone_service._resolve_scheduled_setpoint(zone_name)
            
            if scheduled_setpoint is None:
                print(f"  ⚠️  {zone_name}: No schedule found, skipping")
                continue
            
            # Update to boundary mode with scheduled value
            cursor.execute("""
                UPDATE ZoneStatus
                SET SetpointOverrideMode = 'boundary',
                    SetpointOverrideScheduledValue = ?
                WHERE ZoneName = ?
            """, (scheduled_setpoint, zone_name))
            
            print(f"  ✓ {zone_name}: Converted to boundary mode (scheduled: {scheduled_setpoint}°F)")
            converted += 1
        
        conn.commit()
        print(f"\n✅ Converted {converted} zones to boundary mode")
        print("These overrides will now auto-clear when the schedule changes.")

if __name__ == "__main__":
    main()
