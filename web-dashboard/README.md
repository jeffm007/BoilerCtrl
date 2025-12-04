# Web Dashboard Service

NAS-hosted web dashboard for remote boiler monitoring and control.

## Responsibilities

- Web UI (HTML/CSS/JS frontend)
- API gateway for UI
- WebSocket client to Pi controller
- In-memory caching for performance
- Command queue with retry

## Setup

### Prerequisites

- Docker and Docker Compose (for Synology NAS)
- Or Python 3.12+ for standalone

### Installation

#### Docker (Synology NAS)

```bash
cd web-dashboard
# Edit docker-compose.yml - set PI_WS_URL to your Pi's IP
docker-compose up -d
```

#### Standalone

```bash
cd web-dashboard
python -m venv ../.venv
source ../.venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Edit `docker-compose.yml` or create `.env`:

```env
PI_WS_URL=ws://YOUR_PI_IP:8001/ws
CACHE_TTL=10
LOG_LEVEL=INFO
```

### Run

Docker:
```bash
docker-compose up -d
docker-compose logs -f
```

Standalone:
```bash
python main.py
```

## Access

- Dashboard: http://nas-ip:8000/
- API docs: http://nas-ip:8000/docs
- Health: http://nas-ip:8000/health

## Architecture

- **WebSocket client**: Maintains connection to Pi, handles reconnects
- **In-memory cache**: Stores latest zone states (10s TTL)
- **Command relay**: Sends user commands to Pi via WebSocket
- **Fallback**: Shows "offline" status when Pi disconnected

## API Endpoints

### Web Pages

- `GET /` - Dashboard
- `GET /graphs` - Historical graphs
- `GET /scheduler` - Schedule management
- `GET /metrics` - System metrics

### REST API

- `GET /api/zones` - List all zones (from cache)
- `GET /api/zones/{zone}` - Get zone detail
- `POST /api/zones/{zone}/command` - Send command
- `PUT /api/zones/{zone}` - Update setpoint/mode
- `POST /api/zones/setpoint/uniform` - Set all zones
- `GET /api/connection/status` - Pi connection status
- `GET /health` - Health check

## Performance

- **Cache TTL**: 10 seconds (configurable)
- **Reconnect backoff**: 1s → 60s exponential
- **Command timeout**: 30 seconds
- **Batch interval**: Matches Pi (2 seconds)

## Troubleshooting

- **Pi not connected**: Check PI_WS_URL, network, firewall
- **Cache always stale**: Verify WebSocket messages arriving (check logs)
- **Commands timeout**: Check Pi health endpoint, network latency
- **Container won't start**: Check Docker logs, ensure port 8000 available

## Future Enhancements

- Redis cache for multi-instance deployments
- Read-replica SQLite for history/stats
- Server-Sent Events for UI live updates
- Command persistence queue
