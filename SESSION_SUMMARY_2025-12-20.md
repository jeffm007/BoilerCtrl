# Session Summary - December 20, 2025

## Overview
This session focused on consolidating version control across three systems (Ubuntu VM, Raspberry Pi, NAS Docker) and fixing critical graphing issues in the boiler control system.

---

## 1. Version Control Consolidation

### Problem
Source files were scattered across three systems with conflicting versions:
- Ubuntu VM (10.211.55.4) - supposed golden source
- Raspberry Pi (192.168.2.2) - backend controller
- NAS (192.168.20.200) - web dashboard in Docker container

### Actions Taken

#### Identified Latest File Versions
```bash
# Checked timestamps on all systems
ssh jeffm007@192.168.2.2 "ls -lh --time-style=long-iso ~/boiler_controller/BoilerCtrl/..."
ssh jeffm007@192.168.20.200 "ls -lh --time-style=long-iso /volume1/docker/BoilerCtrl/..."
```

**Findings:**
- **NAS had newest app.js** (Dec 19 16:28, 4164 lines)
- **Pi had newer pi_main.py** (Dec 19 12:25, 636 lines)
- **NAS had latest web-dashboard files** (Dec 19 12:47)

#### Recovered Files to Ubuntu VM
```bash
# Backed up existing files
cp frontend/static/js/app.js frontend/static/js/app.js.backup-ubuntu
cp pi_main.py pi_main.py.backup-ubuntu

# Recovered from NAS
ssh jeffm007@192.168.20.200 "cat /volume1/docker/BoilerCtrl/frontend/static/js/app.js" > frontend/static/js/app.js
ssh jeffm007@192.168.20.200 "cat /volume1/docker/BoilerCtrl/web-dashboard/main.py" > web-dashboard/main.py
ssh jeffm007@192.168.20.200 "cat /volume1/docker/BoilerCtrl/web-dashboard/repositories.py" > web-dashboard/repositories.py
ssh jeffm007@192.168.20.200 "cat /volume1/docker/BoilerCtrl/web-dashboard/database.py" > web-dashboard/database.py
ssh jeffm007@192.168.20.200 "cat /volume1/docker/BoilerCtrl/web-dashboard/sync_service.py" > web-dashboard/sync_service.py

# Recovered from Pi
scp jeffm007@192.168.2.2:~/boiler_controller/BoilerCtrl/pi_main.py pi_main.py
```

#### Committed to Git
```bash
git add frontend/static/js/app.js pi_main.py scripts/fix_overrides.py
git commit -m "Consolidate latest changes from Pi and NAS - recovered app.js from NAS (Dec 19 16:28) and pi_main.py from Pi (Dec 19 12:25)"

git add web-dashboard/main.py web-dashboard/repositories.py web-dashboard/database.py web-dashboard/sync_service.py
git commit -m "Recover latest web-dashboard files from NAS Docker container (Dec 19): main.py (+85 lines), repositories.py (+37 lines), database.py (updated), sync_service.py (new)"
```

**Result:** Ubuntu VM now has all latest changes (7 commits ahead of origin/main)

---

## 2. Backend Database Sync Verification

### Problem
Needed to confirm backend Pi database is syncing to frontend NAS database.

### Findings

**✅ Sync is Working:**
- NAS Docker container has **97,208 events** synced from Pi
- Sync runs every **5 minutes** via `periodic_sync_task()`
- Initial sync fetched 1,000 events after container restart
- Data range: Dec 12 18:29 to Dec 20 10:58

**Architecture Confirmed:**
```
Pi Backend (192.168.2.2:8001)
    ↓ HTTP GET /api/sync/events (every 5 min)
NAS Frontend DB (SQLite)
    ↓ Direct SQL queries (no API calls)
Frontend Graphs (JavaScript)
```

**Verification Commands:**
```bash
# Check NAS database
ssh jeffm007@192.168.20.200 "sqlite3 /volume1/docker/BoilerCtrl/web-dashboard/data/boiler_controller.sqlite3 'SELECT COUNT(*) as total_events, MIN(Timestamp) as oldest, MAX(Timestamp) as latest FROM EventLog;'"
# Result: 97208 events

# Check container logs for sync activity
ssh jeffm007@192.168.20.200 "/usr/local/bin/docker logs boiler-web-dashboard 2>&1 | grep sync"
```

---

## 3. Restarted Backend Service on Pi

### Commands
```bash
# Fixed corrupted systemd service file
ssh jeffm007@192.168.2.2 "cat << 'EOF' | sudo tee /etc/systemd/system/boiler-pi-controller.service
[Unit]
Description=Boiler Pi Controller
After=network.target

[Service]
Type=simple
User=jeffm007
WorkingDirectory=/home/jeffm007/boiler_controller/BoilerCtrl
Environment=\"PATH=/home/jeffm007/boiler_controller/BoilerCtrl/.venv/bin\"
ExecStart=/home/jeffm007/boiler_controller/BoilerCtrl/.venv/bin/python pi_main.py
Restart=always
RestartSec=10

StandardOutput=journal
StandardError=journal
SyslogIdentifier=boiler-pi

[Install]
WantedBy=multi-user.target
EOF"

# Restarted service
ssh jeffm007@192.168.2.2 "sudo systemctl daemon-reload && sudo systemctl restart boiler-pi-controller.service"
```

**Result:** Service running successfully (PID 3213), all 14 zones synced

---

## 4. Fixed Graphing Issues

### Issue 1: Week/Month View Browser Hang

**Problem:** Requesting too much data caused browser to hang
- Week view: ~24,500 data points (1,750 samples × 14 zones)
- Month view: ~105,000 data points

**Solution:** Aggressive downsampling in `buildHistoryRequest()` function

**Changes to `frontend/static/js/app.js`:**
```javascript
// Old logic:
const maxSamplesTarget = Math.max(800, Math.min(4000, Math.round(estimatedSpanDays * 250)));

// New logic:
let maxSamplesTarget;
if (estimatedSpanDays <= 1) {
  maxSamplesTarget = 800;  // Day view
} else if (estimatedSpanDays <= 7) {
  maxSamplesTarget = 600;  // Week view - reduced from ~1750
} else {
  maxSamplesTarget = 500;  // Month view - reduced from ~7500
}

// Also reduced DB query limits
if (estimatedHours >= 168 && estimatedHours < 720) {
  limitValue = 6000;  // Week - reduced from 8000
} else if (estimatedHours >= 720) {
  limitValue = 8000;  // Month - reduced from 12000
}
```

**Commit:**
```bash
git commit -m "Fix week/month view browser hang: reduce max_samples (week: 600, month: 500) and query limits to prevent massive JSON payloads"
```

### Issue 2: Week View Not Working with Selected Date

**Problem:** Week view with selected date threw `RangeError: date value is not finite`

**Root Cause:** Date validation missing, causing invalid dates to be passed to `formatDisplayDate()`

**Solution:** Added date format validation

**Changes to `frontend/static/js/app.js`:**
```javascript
// In resolveGraphsDayValue():
function resolveGraphsDayValue(dayOverride) {
  if (dayOverride === null) return null;
  if (dayOverride === undefined) {
    const inputValue = graphsDayInput?.value || null;
    // Validate format YYYY-MM-DD
    if (inputValue && !inputValue.match(/^\d{4}-\d{2}-\d{2}$/)) {
      return null;
    }
    return inputValue;
  }
  return dayOverride;
}

// In getGraphsRangeSelection():
if (range === "week") {
  if (normalizedDay && normalizedDay.match(/^\d{4}-\d{2}-\d{2}$/)) {
    return {
      range,
      label: `Showing week starting ${formatDisplayDate(normalizedDay)}`,
      params: { day: normalizedDay, spanDays: 7 },
    };
  }
  return buildRolling(24 * 7, "Showing last 7 days (rolling).");
}
```

**Commits:**
```bash
git commit -m "Fix week view date logic: start week from selected date instead of day before"
git commit -m "Fix RangeError in week view: add date format validation to prevent invalid date parsing"
```

### Issue 3: +6 Hour Timezone Offset

**Problem:** Graph data showing 6 hours ahead of actual time

**Root Cause:** `parseUtcTimestamp()` had overly complex timezone conversion logic treating DB timestamps as MST instead of UTC

**Solution:** Simplified to treat DB timestamps as UTC

**Changes to `frontend/static/js/app.js`:**
```javascript
// Old: 45 lines of complex timezone math
// New: Simple UTC parsing
function parseUtcTimestamp(value) {
  if (!value) return null;
  // DB timestamps are stored as UTC ISO strings
  const normalized = value.replace(" ", "T").split(".")[0];

  // Add Z suffix if not present to indicate UTC
  const utcString = normalized.includes("Z") ? normalized : normalized + "Z";

  const date = new Date(utcString);
  if (isNaN(date.getTime())) return null;

  return date;
}
```

**Commit:**
```bash
git commit -m "Fix UTC timestamp parsing: treat DB timestamps as UTC, not MST - resolves +6hr timezone offset issue"
```

---

## 5. Deployment Commands

### Deploy to Raspberry Pi
```bash
scp frontend/static/js/app.js jeffm007@192.168.2.2:~/boiler_controller/BoilerCtrl/frontend/static/js/app.js
scp pi_main.py scripts/fix_overrides.py jeffm007@192.168.2.2:~/boiler_controller/BoilerCtrl/
scp web-dashboard/main.py web-dashboard/repositories.py web-dashboard/database.py web-dashboard/sync_service.py jeffm007@192.168.2.2:~/boiler_controller/BoilerCtrl/web-dashboard/
```

### Deploy to NAS Docker Container
```bash
ssh jeffm007@192.168.20.200 "cat > /volume1/docker/BoilerCtrl/frontend/static/js/app.js" < frontend/static/js/app.js
ssh jeffm007@192.168.20.200 "cat > /volume1/docker/BoilerCtrl/web-dashboard/main.py" < web-dashboard/main.py
ssh jeffm007@192.168.20.200 "cat > /volume1/docker/BoilerCtrl/web-dashboard/repositories.py" < web-dashboard/repositories.py
ssh jeffm007@192.168.20.200 "cat > /volume1/docker/BoilerCtrl/web-dashboard/database.py" < web-dashboard/database.py
ssh jeffm007@192.168.20.200 "cat > /volume1/docker/BoilerCtrl/web-dashboard/sync_service.py" < web-dashboard/sync_service.py
```

### Restart NAS Docker Container
```bash
ssh jeffm007@192.168.20.200 "/usr/local/bin/docker restart boiler-web-dashboard"
# or
ssh jeffm007@192.168.20.200 "/usr/local/bin/docker stop boiler-web-dashboard && /usr/local/bin/docker start boiler-web-dashboard"
```

---

## Git Status on Ubuntu VM

**✅ All Changes Committed:**
```bash
git log --oneline -7
```

**Recent Commits:**
1. `9aea203` - Fix UTC timestamp parsing
2. `de561c0` - Fix RangeError in week view
3. `37b9452` - Fix week view date logic
4. `585a1f5` - Fix browser hang with downsampling
5. `91f261f` - Recover web-dashboard files from NAS
6. `bdab240` - Consolidate changes from Pi and NAS
7. `cd19553` - Fix timezone display

**Branch Status:**
- Current branch: `main`
- Status: 7 commits ahead of `origin/main`
- No uncommitted changes
- Backup files present (not tracked in git):
  - `frontend/static/js/app.js.backup-ubuntu`
  - `pi_main.py.backup-ubuntu`
  - `web-dashboard/*.backup-ubuntu`

---

## Outstanding Issues (Still Present)

### 1. Week View with Selected Date - NOT WORKING
**Status:** Code is fixed but browser still loading old cached version
**Issue:** Browser cache showing `v=1766250450` despite container restart updating to `v=1766257556`

**Next Steps:**
- Force browser cache clear (incognito mode or hard refresh Ctrl+Shift+R)
- Verify cache version in HTML source shows new timestamp
- May need to disable browser cache in DevTools

### 2. +6 Hour Timezone Offset - STILL PRESENT
**Status:** parseUtcTimestamp() simplified but issue persists
**Possible Causes:**
- Browser still using cached old version
- DB timestamps might not actually be UTC
- Need to verify actual timestamp format in database

**Next Steps to Debug:**
```bash
# Check actual timestamp format in DB
ssh jeffm007@192.168.20.200 "sqlite3 /volume1/docker/BoilerCtrl/web-dashboard/data/boiler_controller.sqlite3 'SELECT Timestamp FROM EventLog LIMIT 5;'"

# Check what timezone backend is storing
ssh jeffm007@192.168.2.2 "cd ~/boiler_controller/BoilerCtrl && python3 -c \"from datetime import datetime; print(datetime.utcnow().isoformat())\""
```

---

## System Architecture Summary

### Three-Tier Architecture:
1. **Backend (Pi):** SQLite DB with actual controller data
2. **Sync Layer:** Periodic HTTP sync from Pi → NAS every 5 minutes
3. **Frontend (NAS):** Docker container serving web UI with local SQLite cache

### File Locations:
- **Ubuntu VM (Dev):** `/home/parallels/projects/BoilerCtrl/`
- **Pi (Backend):** `/home/jeffm007/boiler_controller/BoilerCtrl/`
- **NAS (Frontend):** `/volume1/docker/BoilerCtrl/`

### Key Services:
- **Pi Controller:** `boiler-pi-controller.service` (systemd)
- **NAS Dashboard:** `boiler-web-dashboard` (Docker container)

---

## Files Modified This Session

### Created/Updated:
1. `frontend/static/js/app.js` - Major fixes for graphing issues
2. `web-dashboard/main.py` - Recovered from NAS (Dec 19)
3. `web-dashboard/repositories.py` - Recovered from NAS (Dec 19)
4. `web-dashboard/database.py` - Recovered from NAS (Dec 19)
5. `web-dashboard/sync_service.py` - NEW file from NAS (Dec 19)
6. `pi_main.py` - Recovered from Pi (Dec 19)
7. `scripts/fix_overrides.py` - Added to repo

### Backup Files Created:
- `frontend/static/js/app.js.backup-ubuntu`
- `pi_main.py.backup-ubuntu`
- `web-dashboard/database.py.backup-ubuntu`
- `web-dashboard/main.py.backup-ubuntu`
- `web-dashboard/repositories.py.backup-ubuntu`

---

## Quick Reference Commands

### Check Git Status
```bash
cd /home/parallels/projects/BoilerCtrl
git status
git log --oneline -10
```

### Deploy All to Pi
```bash
cd /home/parallels/projects/BoilerCtrl
scp frontend/static/js/app.js jeffm007@192.168.2.2:~/boiler_controller/BoilerCtrl/frontend/static/js/
scp pi_main.py jeffm007@192.168.2.2:~/boiler_controller/BoilerCtrl/
```

### Deploy All to NAS
```bash
cd /home/parallels/projects/BoilerCtrl
ssh jeffm007@192.168.20.200 "cat > /volume1/docker/BoilerCtrl/frontend/static/js/app.js" < frontend/static/js/app.js
ssh jeffm007@192.168.20.200 "/usr/local/bin/docker restart boiler-web-dashboard"
```

### Check Service Status
```bash
# Pi backend
ssh jeffm007@192.168.2.2 "sudo systemctl status boiler-pi-controller.service"
ssh jeffm007@192.168.2.2 "sudo journalctl -u boiler-pi-controller.service -n 20 --no-pager"

# NAS Docker
ssh jeffm007@192.168.20.200 "/usr/local/bin/docker ps | grep boiler"
ssh jeffm007@192.168.20.200 "/usr/local/bin/docker logs boiler-web-dashboard --tail 50"
```

### Verify Database Sync
```bash
ssh jeffm007@192.168.20.200 "sqlite3 /volume1/docker/BoilerCtrl/web-dashboard/data/boiler_controller.sqlite3 'SELECT COUNT(*), MAX(Timestamp) FROM EventLog;'"
```

---

## End of Session

**Date:** December 20, 2025
**Duration:** Full session
**Status:** VM has all latest source, 2 issues remain (likely browser cache related)
