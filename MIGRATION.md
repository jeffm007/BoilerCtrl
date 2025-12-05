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

**Option A: Using Docker (Recommended for Synology NAS)**

```bash
# SSH to your NAS
ssh yourusername@nas-ip

# Create project directory
mkdir -p /volume1/docker/BoilerCtrl
cd /volume1/docker

# Download and extract code
wget https://github.com/jeffm007/BoilerCtrl/archive/refs/heads/main.zip -O BoilerCtrl.zip
unzip BoilerCtrl.zip
mv BoilerCtrl-main BoilerCtrl

# Or copy via tar from dev machine
# On dev machine: cd /path/to/BoilerCtrl; tar -czf - web-dashboard shared frontend | ssh user@nas "cd /volume1/docker/BoilerCtrl && tar -xzf -"

# Navigate to web-dashboard
cd BoilerCtrl/web-dashboard

# Edit docker-compose.yml - set your Pi's VPN IP
vi docker-compose.yml
# Change:
#   PI_WS_URL=ws://YOUR_PI_VPN_IP:8001/ws
#   PI_HTTP_URL=http://YOUR_PI_VPN_IP:8001

# Create required directories
mkdir -p data logs

# Build from parent directory (needed for shared/frontend folders)
cd /volume1/docker/BoilerCtrl

# Create deployment Dockerfile
cat > Dockerfile.web << 'EOF'
FROM python:3.12-slim

WORKDIR /app

COPY web-dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web-dashboard/ /app/
COPY shared/ /app/shared/
COPY frontend/ /app/frontend/

EXPOSE 8000

CMD ["python", "main.py"]
EOF

# Build the image
docker build -t boiler-web-dashboard -f Dockerfile.web .

# Update docker-compose.yml to use pre-built image
cd web-dashboard
sed -i 's/build: \./image: boiler-web-dashboard/' docker-compose.yml

# Start container
docker compose up -d

# Check logs
docker compose logs -f
```

**Option B: Direct Python Installation**

```bash
# Clone repo
cd /volume1/docker
git clone https://github.com/jeffm007/BoilerCtrl.git
cd BoilerCtrl/web-dashboard

# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set environment variables
export PI_WS_URL=ws://YOUR_PI_VPN_IP:8001/ws
export PI_HTTP_URL=http://YOUR_PI_VPN_IP:8001

# Run
python main.py
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

## Feature Status

All features are fully implemented and operational:

- ✅ Zone state monitoring (real-time WebSocket sync)
- ✅ Zone commands (FORCE_ON/OFF, AUTO, THERMOSTAT)
- ✅ Setpoint updates (with sticky input fix)
- ✅ Historical graphs (Chart.js with zone temperature history)
- ✅ Event log timeline (recent events with filtering)
- ✅ Statistics (day/week/month aggregations)
- ✅ Schedule management (view, edit, save, copy to zones)
- ✅ Preset management (save, load, apply, delete)

## Remote Access Setup

### Option 1: Cloudflare Tunnel (Recommended - Free & Secure)

Cloudflare Tunnel provides secure remote access without port forwarding or VPN.

**Prerequisites**:
- Cloudflare account (free tier works)
- Domain name added to Cloudflare DNS

**Setup Steps**:

1. **Install cloudflared on your NAS**:
```bash
# SSH to NAS
ssh jeffm007@192.168.20.200

# Download cloudflared (check latest version at https://github.com/cloudflare/cloudflared/releases)
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x cloudflared-linux-amd64
sudo mv cloudflared-linux-amd64 /usr/local/bin/cloudflared
```

2. **Authenticate with Cloudflare**:
```bash
cloudflared tunnel login
# Opens browser - log in to Cloudflare and select your domain
```

3. **Create a tunnel**:
```bash
cloudflared tunnel create boiler-dashboard
# Note the Tunnel ID shown in output
```

4. **Create tunnel configuration**:
```bash
mkdir -p ~/.cloudflared
cat > ~/.cloudflared/config.yml << 'EOF'
tunnel: <YOUR_TUNNEL_ID>
credentials-file: /root/.cloudflared/<YOUR_TUNNEL_ID>.json

ingress:
  - hostname: boiler.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
EOF
```

5. **Create DNS record**:
```bash
cloudflared tunnel route dns boiler-dashboard boiler.yourdomain.com
```

6. **Run tunnel as a service**:
```bash
# Install as system service
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared

# Check status
sudo systemctl status cloudflared
```

7. **Access your dashboard**:
   - From anywhere: `https://boiler.yourdomain.com`
   - Cloudflare automatically provides SSL/TLS certificate
   - No port forwarding needed
   - Works from iPhone, any browser

**Advantages**:
- ✅ No port forwarding required
- ✅ Free SSL/TLS certificate (automatic HTTPS)
- ✅ DDoS protection included
- ✅ No public IP exposure
- ✅ Works behind CGNAT/restrictive networks
- ✅ Can add Cloudflare Access for authentication

### Option 2: Port Forwarding (Simple but Less Secure)

1. **Forward port on TX router**:
   - External: 8000 → Internal: 192.168.20.200:8000
2. **Get public IP**: Check router or Google "what is my ip"
3. **Optional DDNS**: Set up DuckDNS or No-IP for dynamic IP
4. **Access**: `http://YOUR_PUBLIC_IP:8000`

⚠️ **Security Warning**: Requires authentication (see below)

### Option 3: Synology VPN Server

1. Install "VPN Server" package in DSM
2. Configure OpenVPN server
3. Install OpenVPN client on iPhone
4. Connect to VPN, access `http://192.168.20.200:8000`

### Adding Authentication (Recommended for Public Access)

If using port forwarding or want extra security with Cloudflare:

**Option A: Cloudflare Access** (Works with Cloudflare Tunnel):
```bash
# In Cloudflare dashboard → Zero Trust → Access → Applications
# Add application for boiler.yourdomain.com
# Configure authentication (email OTP, Google, etc.)
```

**Option B: Add Basic Auth to Web Dashboard**:
- Update `web-dashboard/main.py` with authentication middleware
- Require username/password for all endpoints

## Next Steps

1. **Set up remote access**: Deploy Cloudflare Tunnel or configure port forwarding
2. **Add authentication**: Cloudflare Access or basic auth middleware
3. **Monitor system performance**: WebSocket connection stability, command latency
4. **Configure firewall rules**: Lock down Pi controller to only accept VPN connections
5. **Set up monitoring**: Health checks, uptime monitoring, alerting
6. **Regular backups**: Database and configuration files

## Troubleshooting

### Dashboard shows "No data available"

- Check `/api/connection/status` endpoint
- Verify `PI_WS_URL` is correct in docker-compose.yml
- Test WebSocket: `curl http://pi-ip:8001/health`
- Check firewall/VPN connectivity
- Verify both `PI_WS_URL` and `PI_HTTP_URL` environment variables are set

### Commands timeout

- Increase `COMMAND_TIMEOUT` in NAS config (default: 10s)
- Check network latency: `ping pi-ip`
- Verify Pi is processing commands (check Pi logs)

### Frequent disconnects

- Check network stability between Pi and NAS
- Review WebSocket reconnection logs
- Consider increasing reconnect backoff times
- Ensure VPN tunnel is stable

### Graphs/Metrics/Scheduler tabs show no data

- Verify `PI_HTTP_URL` environment variable is set correctly
- Check NAS logs: `docker compose logs -f`
- Test HTTP endpoint: `curl http://pi-ip:8001/api/zones`
- Ensure Pi Controller is running and accessible

### Container fails to start

**"Directory '/frontend/static' does not exist"**
- Build from parent directory: `cd /volume1/docker/BoilerCtrl && docker build -t boiler-web-dashboard -f Dockerfile.web .`
- Ensure frontend/ and shared/ folders were copied to NAS

**"Connection refused" errors**
- Verify `PI_WS_URL` uses Pi's VPN IP, not localhost
- Check Pi Controller is running: `curl http://pi-vpn-ip:8001/health`
- Verify VPN tunnel is up and routes are correct

### OpenVPN/VPN Issues

**Can't find VPN IP**
- Windows: `Get-NetIPAddress | Where-Object {$_.InterfaceAlias -like "*OpenVPN*" -or $_.InterfaceAlias -like "*TAP*"}`
- Linux: `ip addr show tun0` or `ifconfig tun0`
- Check OpenVPN client status/logs

**NAS can't reach Pi**
- From NAS: `ping pi-vpn-ip`
- Test port: `nc -zv pi-vpn-ip 8001` or `telnet pi-vpn-ip 8001`
- Check firewall rules on both ends
