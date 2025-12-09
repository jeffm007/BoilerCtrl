#!/bin/bash
#
# Setup script for PostgreSQL on Raspberry Pi
# This script installs PostgreSQL, creates the boiler database, and configures remote access
#

set -e  # Exit on any error

echo "====================================="
echo "Boiler Controller - PostgreSQL Setup"
echo "====================================="
echo

# Check if running on Raspberry Pi
if [ ! -f /proc/cpuinfo ] || ! grep -q "Raspberry Pi" /proc/cpuinfo; then
    echo "Warning: This script is designed for Raspberry Pi"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update package lists
echo "Step 1: Updating package lists..."
sudo apt-get update

# Install PostgreSQL
echo "Step 2: Installing PostgreSQL..."
sudo apt-get install -y postgresql postgresql-contrib

# Start PostgreSQL service
echo "Step 3: Starting PostgreSQL service..."
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database and user
echo "Step 4: Setting up database and user..."
read -p "Enter database name [boiler_controller]: " DB_NAME
DB_NAME=${DB_NAME:-boiler_controller}

read -p "Enter database username [boiler_user]: " DB_USER
DB_USER=${DB_USER:-boiler_user}

read -sp "Enter database password: " DB_PASSWORD
echo

if [ -z "$DB_PASSWORD" ]; then
    echo "Error: Password cannot be empty"
    exit 1
fi

# Get Pi's VPN IP address
echo "Step 5: Detecting VPN IP address..."
VPN_IP=$(ip addr show tun0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "")

if [ -z "$VPN_IP" ]; then
    echo "Warning: Could not detect VPN interface (tun0)"
    read -p "Enter your Pi's VPN IP address: " VPN_IP
fi

echo "VPN IP detected: $VPN_IP"

# Create PostgreSQL user and database
sudo -u postgres psql <<EOF
-- Create user
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';

-- Create database
CREATE DATABASE $DB_NAME OWNER $DB_USER;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;

\q
EOF

echo "Database '$DB_NAME' and user '$DB_USER' created successfully!"

# Configure PostgreSQL for remote connections
echo "Step 6: Configuring PostgreSQL for remote access..."

# Find PostgreSQL version
PG_VERSION=$(psql --version | grep -oP '\d+' | head -1)
PG_CONF_DIR="/etc/postgresql/$PG_VERSION/main"

# Backup original configuration
sudo cp "$PG_CONF_DIR/postgresql.conf" "$PG_CONF_DIR/postgresql.conf.bak"
sudo cp "$PG_CONF_DIR/pg_hba.conf" "$PG_CONF_DIR/pg_hba.conf.bak"

# Update postgresql.conf to listen on all interfaces
sudo sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" "$PG_CONF_DIR/postgresql.conf"

# Add entry to pg_hba.conf for VPN network
VPN_NETWORK=$(echo $VPN_IP | sed 's/\.[0-9]*$/\.0\/24/')
echo "host    $DB_NAME    $DB_USER    $VPN_NETWORK    md5" | sudo tee -a "$PG_CONF_DIR/pg_hba.conf"

# Restart PostgreSQL
echo "Step 7: Restarting PostgreSQL..."
sudo systemctl restart postgresql

# Create .env file for database connection
echo "Step 8: Creating .env configuration..."
ENV_FILE="$HOME/.boiler_controller.env"

cat > "$ENV_FILE" <<EOF
# PostgreSQL Database Configuration
DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME

# For remote clients, use:
# DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@$VPN_IP:5432/$DB_NAME

# Other settings
BOILER_HARDWARE_MODE=gpio
BOILER_TIME_ZONE=America/Denver
EOF

chmod 600 "$ENV_FILE"

echo
echo "====================================="
echo "PostgreSQL Setup Complete!"
echo "====================================="
echo
echo "Database Details:"
echo "  Name: $DB_NAME"
echo "  User: $DB_USER"
echo "  Host: $VPN_IP (VPN) or localhost (local)"
echo "  Port: 5432"
echo
echo "Connection string saved to: $ENV_FILE"
echo
echo "Remote connection string for your Windows machine:"
echo "  DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@$VPN_IP:5432/$DB_NAME"
echo
echo "Next steps:"
echo "  1. Source the environment file: source $ENV_FILE"
echo "  2. Initialize the database: python -m backend.database"
echo "  3. On your Windows machine, set DATABASE_URL in .env"
echo
echo "To test the connection:"
echo "  psql -h $VPN_IP -U $DB_USER -d $DB_NAME"
echo

