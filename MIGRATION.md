# Migration Guide: Monolith → Distributed Architecture

This guide explains how to migrate from the single-server setup to the distributed Pi + NAS architecture.

## Overview

**Before**: Single FastAPI server running on Pi, accessed via port forwarding or VPN

**After**:
- Pi Controller (CO): Hardware + data + WebSocket server
- Web Dashboard (TX): UI + cache + WebSocket client

## Migration Steps

### 1. Backup Current System

```bash
# Backup database
cp data/boiler_controller.sqlite3 data/boiler_controller.backup.sqlite3

# Backup config
cp config/zones.json config/zones.backup.json
```

### 2. Update Code on Pi

```bash
cd /home/pi/boiler-controller

# Pull latest code
git pull origin main

# Install dependencies
source .venv/bin/activate
pip install -r pi-controller/requirements.txt
pip install websockets

# Test Pi controller
cd pi-controller
python main.py
```

Verify:
- http://pi-ip:8001/health should return `{"status": "healthy", ...}`
- WebSocket server running on port 8001

### 3. Deploy NAS Dashboard

On Synology NAS:

```bash
# Clone repo
cd /volume1/docker
git clone https://github.com/yourusername/BoilerCtrl.git
cd BoilerCtrl/web-dashboard

# Edit docker-compose.yml
# Set PI_WS_URL=ws://YOUR_PI_IP:8001/ws

# Start container
docker-compose up -d

# Check logs
docker-compose logs -f
```

Verify:
- http://nas-ip:8000/health should show Pi connection status
- http://nas-ip:8000/ should load dashboard
- Check `/api/connection/status` shows `"connected": true`

### 4. Configure Networking

#### Option A: VPN Tunnel (Recommended)

Set up WireGuard between Pi and NAS:

```bash
# On both Pi and NAS
sudo apt install wireguard

# Generate keys and configure tunnel
# Use VPN IPs in PI_WS_URL
```

#### Option B: Port Forwarding

Forward port 8001 on Pi's router:
- External port: 8001
- Internal IP: Pi's local IP
- Internal port: 8001

Update `PI_WS_URL` to use public IP or DDNS hostname.

### 5. Migrate Data Collection Scripts

If you have custom scripts posting to `/api/zones/{zone}/events`:

**No changes needed** - Pi controller maintains same REST endpoints on port 8001.

### 6. Update Systemd Service

```bash
# On Pi
sudo cp pi-controller/boiler-pi-controller.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable boiler-pi-controller
sudo systemctl start boiler-pi-controller
sudo systemctl status boiler-pi-controller
```

### 7. Test End-to-End

1. Open dashboard: http://nas-ip:8000/
2. Verify zones show current state
3. Try a command (e.g., FORCE_ON a zone)
4. Confirm command executes on Pi
5. Check dashboard updates

### 8. Monitor for 24 Hours

Watch logs on both sides:

```bash
# Pi
sudo journalctl -u boiler-pi-controller -f

# NAS
docker-compose logs -f
```

Look for:
- Connection stability
- Command success rate
- State update latency

## Rollback Plan

If issues occur:

```bash
# On Pi: Stop new service, start old monolith
sudo systemctl stop boiler-pi-controller
cd /home/pi/boiler-controller
source .venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# On NAS: Point to Pi's old API
# (Edit docker-compose or use VPN to access Pi:8000)
```

## What's Not Migrated Yet

These features require additional implementation:

- ✅ Zone state monitoring
- ✅ Zone commands
- ✅ Setpoint updates
- ❌ Historical graphs (requires replica DB sync)
- ❌ Event log timeline (requires replica DB sync)
- ❌ Statistics (requires replica DB sync)
- ❌ Schedule management (requires Pi API endpoints)
- ❌ Preset management (requires Pi API endpoints)

## Next Steps

1. **Add database replication**: Sync SQLite from Pi to NAS
2. **Implement remaining APIs**: schedules, presets, history on Pi
3. **Add Redis caching**: For multi-instance NAS deployments
4. **Setup monitoring**: Prometheus + Grafana for metrics
5. **Enable TLS**: Secure WebSocket with wss://

## Troubleshooting

### Dashboard shows "No data available"

- Check `/api/connection/status`
- Verify `PI_WS_URL` is correct
- Test: `curl http://pi-ip:8001/health`
- Check firewall/VPN

### Commands timeout

- Increase `COMMAND_TIMEOUT` in NAS config
- Check network latency: `ping pi-ip`
- Verify Pi is processing commands (check logs)

### Frequent disconnects

- Check network stability
- Adjust reconnect backoff
- Consider VPN instead of public internet

### Cache always stale

- Verify WebSocket messages arriving (NAS logs)
- Check Pi batch interval
- Ensure Pi has zones in database
