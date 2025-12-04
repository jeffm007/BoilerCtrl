# Distributed Architecture Guide

## Overview

The Boiler Controller is split into two services for distributed operation:

### Pi Controller (Colorado)
- **Location**: Raspberry Pi at boiler site
- **Responsibilities**:
  - Hardware control (relays, sensors)
  - Primary SQLite database
  - Auto-control logic
  - WebSocket server for state publishing
  - Command execution API

### Web Dashboard (Texas)
- **Location**: Synology NAS
- **Responsibilities**:
  - Web UI (HTML/CSS/JS)
  - Read-replica SQLite (synced from Pi)
  - Command queue with retry
  - WebSocket client for state subscription
  - Local caching for performance

## Communication Architecture

### Real-time Sync (Pi → NAS)
- **Protocol**: WebSocket with JSON messages
- **Batching**: State updates batched every 1-5 seconds
- **Compression**: gzip for payloads >1KB
- **Reliability**: Sequence numbers, gap detection, auto-reconnect

### Command Flow (NAS → Pi)
- **Protocol**: REST API with command queue
- **Timeout**: 30s per command
- **Retry**: 3 attempts with exponential backoff
- **Fallback**: Queue persisted during disconnects

### Message Types
1. **zone_state_update**: Batched zone states (Pi → NAS)
2. **system_state_update**: System status (Pi → NAS)
3. **event_log_entry**: New event logged (Pi → NAS)
4. **command_request**: User command (NAS → Pi)
5. **command_response**: Command result (Pi → NAS)
6. **heartbeat**: Health check every 30s
7. **full_sync_request**: On reconnect (NAS → Pi)
8. **full_sync_response**: Full state dump (Pi → NAS)

## Data Flow

### Normal Operation
```
Pi: Hardware event → Update local DB → Batch → WebSocket publish
NAS: Receive batch → Update replica → Update UI cache → Render
```

### User Command
```
NAS: UI action → Queue command → Send via WS → Wait for response
Pi: Receive command → Validate → Execute → Update DB → Respond
NAS: Receive response → Update UI
```

### Disconnection Handling
```
Pi: Continue autonomous operation, queue events
NAS: Show "offline" status, queue commands locally
On reconnect: Full sync, replay queued commands
```

## Performance Optimizations

### Batching
- Zone states: every 1-5s (configurable)
- Events: immediate for ON/OFF, batched for SAMPLE
- Max batch size: 100 updates

### Caching (NAS)
- Redis cache for current zone states (TTL: 10s)
- In-memory cache for recent events (last 1000)
- Static asset CDN via Synology

### Compression
- gzip for messages >1KB
- Delta sync: only changed zones
- Deduplication: skip identical consecutive states

### Database
- Pi: WAL mode, busy_timeout 5s
- NAS: Read-only replica, periodic full sync
- Indexes on timestamp, zone_name, event

## Reliability Features

### Connection Management
- Auto-reconnect with exponential backoff (1s → 60s)
- Heartbeat every 30s
- Connection timeout: 90s

### Command Reliability
- Unique command IDs (UUID)
- 30s timeout per command
- 3 retry attempts
- Dead letter queue for failed commands

### Autonomous Pi Operation
- Continues normal operation when disconnected
- Queues events up to 10,000 (FIFO)
- Auto-control logic runs locally
- No dependency on NAS

### Data Integrity
- Sequence numbers for message ordering
- Checksum validation
- Duplicate detection
- Gap detection triggers full sync

## Deployment

### Pi Controller
```bash
# systemd service
sudo systemctl enable boiler-pi-controller
sudo systemctl start boiler-pi-controller
```

### NAS Web Dashboard
```bash
# Docker Compose
docker-compose up -d web-dashboard
```

## Configuration

### Pi (`pi-controller/.env`)
```
DB_PATH=/var/lib/boiler/boiler_controller.sqlite3
WS_HOST=0.0.0.0
WS_PORT=8001
BATCH_INTERVAL=2.0
HEARTBEAT_INTERVAL=30.0
LOG_LEVEL=INFO
```

### NAS (`web-dashboard/.env`)
```
PI_WS_URL=ws://pi.example.com:8001/ws
DB_PATH=/volume1/docker/boiler/replica.sqlite3
REDIS_URL=redis://localhost:6379/0
CACHE_TTL=10
COMMAND_TIMEOUT=30
LOG_LEVEL=INFO
```

## Monitoring

### Health Endpoints
- Pi: `GET /health` → {status, uptime, db_size, memory}
- NAS: `GET /health` → {status, pi_connected, cache_hit_rate}

### Metrics
- Message throughput (msg/s)
- Command latency (p50, p95, p99)
- Connection uptime (%)
- Cache hit rate (%)
- Database replica lag (seconds)

## Security

### Network
- VPN tunnel between sites (WireGuard recommended)
- TLS for WebSocket (wss://)
- Firewall rules: only Pi → NAS and NAS → Pi

### Authentication
- Shared secret for WebSocket handshake
- API key for command execution
- Rate limiting on both ends

### Data
- Encrypted database at rest
- Encrypted messages in transit
- Audit log for all commands
