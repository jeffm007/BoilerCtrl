# Boiler Controller Web Server

This repository contains a FastAPI-based web server for monitoring and controlling a 14‑zone hydronic boiler system that reports the following signals:

- Zone `Call for Heat` state (detected via optically isolated 24 VAC inputs).
- Room temperature for each zone.
- Supply pipe temperature for each zone.
- Boiler firing (burner) state.

The application exposes a REST API and a lightweight dashboard UI. Data is persisted in SQLite so the Pi can operate offline. A hardware abstraction layer lets the same code run without GPIO hardware (helpful for development and unit testing).

## Features

- **Real-time monitoring** of the 14 zones and boiler status.
- **Historical logging** of every state change with associated room, pipe, and outdoor temperatures.
- **Manual overrides** to force a zone on/off or switch between AUTO and MANUAL control modes.
- **Configurable setpoints** per zone (stored in the database).
- **Inline setpoint editing** directly from the dashboard with live persistence.
- **Simple dashboard** served from the Pi for local control and visualization.
- **Zone summary metrics** (daily calls, runtime, average temp) for quick diagnostics.

## Project Layout

```
backend/
  main.py              # FastAPI application entry point
  config.py            # Runtime configuration options
  database.py          # SQLite initialization and helpers
  models.py            # Low-level SQL helpers / constants
  repositories.py      # Data access layer (CRUD helpers)
  schemas.py           # Pydantic request/response models
  services/
    zone_service.py    # Orchestrates zone logic and persistence
    event_service.py   # Records and queries event log entries
  hardware/
    controller.py      # Abstraction for relay + GPIO operations
frontend/
  templates/
    index.html         # Dashboard UI
  static/
    css/style.css      # Basic styling
    js/app.js          # API integrations + live updates
requirements.txt       # Python dependencies
```

## Getting Started

1. **Setup environment**

   ```pwsh
   python -m venv .venv
   . ".\.venv\Scripts\Activate.ps1"
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

2. **Run database migrations (first boot only)**

   ```bash
   python -m backend.database
   ```

3. **Load sample data (optional)**

   ```bash
   python -m scripts.seed_sample_data
   ```

   Room names are configurable via `config/zones.json`. Edit that file (or set
   the `BOILER_ZONE_CONFIG` environment variable to point at your own JSON) to
   map each zone to a friendly description. The dashboard and event log both
   display the `room` column using this mapping.

3. **Start the server**

   ```bash
   uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   ## Linting & Formatting

   - Tools: Ruff (lint), Black (format), Isort (imports). Configured in `pyproject.toml`.
   - Run linters locally:

   ```pwsh
   . ".\.venv\Scripts\Activate.ps1"
   python -m ruff check .
   python -m black --check .
   python -m isort --check-only .
   ```

   - Auto-fix formatting:

   ```pwsh
   . ".\.venv\Scripts\Activate.ps1"
   python -m isort .
   python -m black .
   ```

   ## Pre-commit Hooks

   - Install and enable hooks:

   ```pwsh
   . ".\.venv\Scripts\Activate.ps1"
   python -m pre_commit install
   ```

   - Run hooks on all files (optional):

   ```pwsh
   . ".\.venv\Scripts\Activate.ps1"
   python -m pre_commit run --all-files
   ```

   CI runs `ruff`, `black --check`, and `isort --check-only` on every push/PR.
   ```

4. **Access the dashboard**

   - Dashboard UI: <http://localhost:8000/>
   - Interactive API docs: <http://localhost:8000/docs>

## Hardware Integration

The hardware layer is abstracted behind `hardware.controller.BaseHardwareController`. The default implementation (`MockHardwareController`) simulates relays in memory. To use real hardware (e.g., Raspberry Pi GPIO over `pigpio`), create a class that inherits from `BaseHardwareController` and update `config.py` to instantiate it.

```
class PigpioHardwareController(BaseHardwareController):
    def __init__(self, config: HardwareConfig):
        ...

    def set_zone_state(self, zone: str, state: bool) -> None:
        ...
```

## Data Model Overview

Two complementary tables are used:

- `ZoneStatus`: one row per zone storing the latest state, temperatures, setpoint, and control mode.
- `SystemStatus`: single-row table for system-wide metrics such as outdoor temperature.
- `EventLog`: append-only log with `ON`/`OFF` events, burner cycles, and associated temperature snapshots.

See `backend/database.py` for schema creation.

## Next Steps

- Implement the hardware controller for your specific relay + optocoupler wiring.
- Hook your real-time data collection script to call the REST endpoints (or directly use the repository layer).
- Extend the frontend with richer charts (e.g., Plotly) and authentication if remote access is required.
# BoilerCtrl
