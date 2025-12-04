# Pi Controller Service

Raspberry Pi service for boiler hardware control and state publishing.

## Responsibilities

- Hardware control (GPIO relays, sensor reading)
- Primary SQLite database
- Auto-control logic
- WebSocket server for state publishing to NAS
- Local REST API for data collection scripts

## Setup

### Prerequisites

- Raspberry Pi (tested on Pi 4)
- Python 3.12+
- Sensors and relay hardware connected

### Installation

```bash
cd pi-controller
python -m venv ../.venv
source ../.venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Create `.env` file:

```env
DB_PATH=/var/lib/boiler/boiler_controller.sqlite3
WS_HOST=0.0.0.0
WS_PORT=8001
BATCH_INTERVAL=2.0
HEARTBEAT_INTERVAL=30.0
LOG_LEVEL=INFO
```

### Run

Development:
```bash
python main.py
```

Production (systemd):
```bash
sudo cp boiler-pi-controller.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable boiler-pi-controller
sudo systemctl start boiler-pi-controller
```

Check status:
```bash
sudo systemctl status boiler-pi-controller
sudo journalctl -u boiler-pi-controller -f
```

## API Endpoints

### WebSocket

- `ws://pi-ip:8001/ws` - State publishing and command reception

### REST (Local)

- `POST /api/zones/{zone_name}/events` - Record zone event
- `POST /api/boiler/events` - Record boiler event
- `GET /health` - Health check

## WebSocket Protocol

See `../shared/schemas.py` for message formats.

### Outgoing (Pi → NAS)

- `zone_state_update` - Batched zone states
- `full_sync_response` - Full state on connect
- `heartbeat` - Health status

### Incoming (NAS → Pi)

- `command_request` - Execute command
- `heartbeat` - Keep-alive ping

## Hardware Integration

Edit `main.py` to replace `MockHardwareController` with your real hardware implementation:

```python
from backend.hardware.controller import PigpioHardwareController

hw_controller = PigpioHardwareController(config)
```

## Troubleshooting

- **No WebSocket clients**: Check firewall, ensure port 8001 is accessible
- **Database locked**: Increase busy_timeout in database.py
- **Auto-control not running**: Check logs for exceptions in auto_control_loop
