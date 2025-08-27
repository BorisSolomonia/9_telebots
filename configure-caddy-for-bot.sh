#!/bin/bash

# Configure existing Caddy on VM to proxy /health/bot to port 8081
# Run this script on the VM once to add bot health endpoint

set -euo pipefail

echo "Configuring existing Caddy to proxy to bot on port 8081..."

# Check if Caddy is running
if ! docker ps | grep -q caddy; then
    echo "❌ Caddy container not found. Make sure Caddy is running first."
    exit 1
fi

# Add bot health endpoint to existing Caddyfile
CADDY_CONFIG_DIR="/opt/caddy"  # Adjust this path based on your Caddy setup

# Create a snippet for bot proxying
cat > /tmp/bot-proxy.caddy << 'EOF'
# Bot health endpoint - add this to your main Caddyfile
handle /health/bot {
    reverse_proxy localhost:8081
}

# Optional: Bot API endpoints
handle /api/bot/* {
    reverse_proxy localhost:8081 {
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }
}
EOF

echo "✅ Created bot proxy configuration snippet at /tmp/bot-proxy.caddy"
echo ""
echo "Add this to your existing Caddyfile:"
echo "=================================="
cat /tmp/bot-proxy.caddy
echo "=================================="
echo ""
echo "Then reload Caddy with:"
echo "docker exec <caddy-container-name> caddy reload --config /etc/caddy/Caddyfile"
echo ""
echo "The bot will be accessible at:"
echo "- Health check: http://your-vm-ip/health/bot"
echo "- API endpoints: http://your-vm-ip/api/bot/*"