# Setpoint Override System - Enhanced Features

## Overview
The setpoint override system has been enhanced to support three intelligent override modes when manually adjusting setpoints in AUTO mode:

## Override Modes

### 1. Boundary Mode (Default)
- **Behavior**: Override persists until the next schedule boundary
- **Use Case**: Temporary adjustment that should revert when the next scheduled setpoint change occurs
- **How it works**: System detects when the scheduled setpoint changes and automatically clears the override
- **Example**: User sets 72°F at 2pm, schedule changes to 68°F at 10pm → override automatically clears at 10pm

### 2. Permanent Mode
- **Behavior**: Override persists indefinitely until manually cleared
- **Use Case**: Long-term setpoint adjustment that ignores the schedule
- **How it works**: Manual setpoint remains active regardless of schedule changes
- **Example**: User sets 70°F and wants it to stay there until they manually change it again

### 3. Timed Mode
- **Behavior**: Override persists until a specific datetime
- **Use Case**: Temporary adjustment with a known end time
- **How it works**: System automatically clears override and returns to schedule at specified time
- **Example**: User sets 75°F until 6:00 PM, then returns to normal schedule

## Database Schema Changes

### New Columns in ZoneStatus Table
1. **SetpointOverrideMode**: TEXT/VARCHAR
   - Values: 'boundary', 'permanent', 'timed'
   - Indicates which override mode is active

2. **SetpointOverrideUntil**: TEXT/TIMESTAMP
   - Stores the expiration datetime for 'timed' mode overrides
   - NULL for 'boundary' and 'permanent' modes

3. **SetpointOverrideAt**: TEXT/TIMESTAMP (existing, enhanced)
   - Records when the override was created
   - Used for all three modes

## API Changes

### ZoneUpdateRequest Schema
```json
{
  "target_setpoint_f": 72.0,
  "override_mode": "boundary",  // optional: "boundary", "permanent", "timed"
  "override_until": "2025-12-09T18:00:00"  // required for "timed" mode
}
```

## Backend Logic

### When User Changes Setpoint in AUTO Mode
1. System records current datetime in `SetpointOverrideAt`
2. Sets `SetpointOverrideMode` based on user selection (default: "boundary")
3. If mode is "timed", stores expiration time in `SetpointOverrideUntil`
4. Updates `TargetSetpoint_F` to user's value

### During Polling (_sync_auto_setpoint)
The system checks active overrides in this order:

1. **Timed Mode Check**:
   - If `override_until` datetime has passed → clear override, apply schedule
   - If still valid → keep user's setpoint

2. **Permanent Mode Check**:
   - Always keep user's setpoint, ignore schedule

3. **Boundary Mode Check**:
   - Compare current schedule setpoint to zone's setpoint
   - If schedule changed (difference > 0.05°F) → clear override, apply new schedule
   - If schedule unchanged → keep user's setpoint

4. **No Override**:
   - Apply schedule setpoint normally

## Files Modified

### Database Layer
- `backend/database.py`: Added schema columns and migration functions
  - `_ensure_override_mode_column()`
  - `_ensure_override_until_column()`

### Repository Layer
- `backend/repositories.py`: Updated data access methods
  - `update_zone_status()` now accepts `setpoint_override_mode` and `setpoint_override_until`
  - `clear_override` parameter clears all three override columns

### Service Layer
- `backend/services/zone_service.py`: Enhanced business logic
  - `update_zone()`: Detects AUTO mode, parses override parameters
  - `_sync_auto_setpoint()`: Implements three-mode override logic

### API Layer
- `backend/schemas.py`: Updated request models
  - `ZoneUpdateRequest`: Added `override_mode` and `override_until` fields

## Migration

Run the database migration to add new columns:
```bash
python -m backend.database
```

This will:
- Add `SetpointOverrideMode` column to ZoneStatus table
- Add `SetpointOverrideUntil` column to ZoneStatus table

## Frontend Integration (TODO)

The frontend will need to be updated to:
1. Add UI controls for selecting override mode
2. Add datetime picker for "timed" mode
3. Send `override_mode` and `override_until` in API requests
4. Display active override status and expiration time

## Testing Recommendations

1. **Boundary Mode**:
   - Set override, verify it persists through polling
   - Wait for schedule change, verify override clears

2. **Permanent Mode**:
   - Set override, verify it persists through multiple schedule changes

3. **Timed Mode**:
   - Set override with future expiration
   - Verify it persists until expiration
   - Verify it clears automatically after expiration

## Benefits

- **Flexibility**: Users choose how long their adjustments persist
- **Convenience**: No need to manually revert temporary changes
- **Predictability**: Clear behavior for each mode
- **Schedule Integrity**: Schedule remains the source of truth unless explicitly overridden
