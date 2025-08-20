#!/bin/bash
# VM Startup Script for Telegram Bots
# Based on 9-Tones architecture from DEPLOY.md

set -e

echo "🚀 Setting up VM for Telegram Bots deployment..."

# Update system
echo "📦 Updating system packages..."
apt-get update && apt-get upgrade -y

# Install Docker
echo "🐳 Installing Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker $USER

# Install Docker Compose
echo "🐙 Installing Docker Compose..."
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Install Google Cloud SDK
echo "☁️ Installing Google Cloud SDK..."
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# Add gcloud to PATH for current session
export PATH=$PATH:/root/google-cloud-sdk/bin

# Configure Docker for Artifact Registry
echo "🔐 Configuring Docker for GCP..."
gcloud auth configure-docker europe-west3-docker.pkg.dev

# Create shared Docker resources
echo "🌐 Creating Docker networks and volumes..."
docker network create web 2>/dev/null || true
docker volume create caddy_data 2>/dev/null || true

# Setup deployment directory
echo "📁 Setting up deployment directories..."
mkdir -p /opt/apps/telegram-bots
chown -R $USER:$USER /opt/apps

# Create logs directory
mkdir -p /opt/apps/telegram-bots/logs
chmod 755 /opt/apps/telegram-bots/logs

# Install monitoring tools
echo "📊 Installing monitoring tools..."
apt-get install -y htop curl wget jq

# Setup firewall rules
echo "🔥 Configuring firewall..."
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Create deployment helper script
cat > /opt/apps/telegram-bots/deploy-bots.sh << 'EOF'
#!/bin/bash
# Telegram Bots Deployment Helper Script

PROJECT_ID="${GCP_PROJECT_ID:-nine-tones-bots-2025}"
DEPLOY_DIR="/opt/apps/telegram-bots"

echo "🤖 Deploying Telegram Bots..."

cd $DEPLOY_DIR

# Fetch secrets from Secret Manager
echo "🔐 Fetching secrets..."
gcloud secrets versions access latest \
  --secret="telegram-bots-env" \
  --project=$PROJECT_ID > .env

# Pull latest images
echo "📥 Pulling latest images..."
gcloud auth configure-docker europe-west3-docker.pkg.dev --quiet
docker compose pull

# Deploy
echo "🚀 Starting deployment..."
docker compose down --remove-orphans
docker compose up -d --wait

# Show status
echo "📊 Deployment status:"
docker compose ps
docker compose logs --tail=20

echo "✅ Telegram bots deployment completed!"
EOF

chmod +x /opt/apps/telegram-bots/deploy-bots.sh

# Create monitoring script
cat > /opt/apps/telegram-bots/monitor-bots.sh << 'EOF'
#!/bin/bash
# Telegram Bots Monitoring Script

DEPLOY_DIR="/opt/apps/telegram-bots"

echo "📊 TELEGRAM BOTS MONITORING DASHBOARD"
echo "===================================="
echo ""

cd $DEPLOY_DIR

echo "🐳 Container Status:"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo ""

echo "💾 Resource Usage:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" payment-bot order-bot caddy
echo ""

echo "🌐 Health Checks:"
# Test main health endpoint
if curl -f -m 5 http://localhost/health >/dev/null 2>&1; then
    echo "✅ Main health check: PASS"
else
    echo "❌ Main health check: FAIL"
fi

# Test bot status endpoints
if curl -f -m 5 http://localhost/bots/payment/status >/dev/null 2>&1; then
    echo "✅ Payment bot status: PASS"
else
    echo "⚠️ Payment bot status: UNAVAILABLE"
fi

if curl -f -m 5 http://localhost/bots/order/status >/dev/null 2>&1; then
    echo "✅ Order bot status: PASS"
else
    echo "⚠️ Order bot status: UNAVAILABLE"
fi
echo ""

echo "📋 Recent Logs (last 10 lines):"
docker compose logs --tail=10
EOF

chmod +x /opt/apps/telegram-bots/monitor-bots.sh

# Create systemd service for auto-restart
cat > /etc/systemd/system/telegram-bots.service << 'EOF'
[Unit]
Description=Telegram Bots Service
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=true
WorkingDirectory=/opt/apps/telegram-bots
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

systemctl enable telegram-bots.service

# Setup log rotation
cat > /etc/logrotate.d/telegram-bots << 'EOF'
/opt/apps/telegram-bots/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    copytruncate
}
EOF

# Create cron job for monitoring
cat > /etc/cron.d/telegram-bots-monitor << 'EOF'
# Monitor telegram bots every 5 minutes
*/5 * * * * root /opt/apps/telegram-bots/monitor-bots.sh >> /var/log/telegram-bots-monitor.log 2>&1
EOF

echo "✅ VM setup completed!"
echo ""
echo "📋 Next steps:"
echo "1. Run: gcloud auth login"
echo "2. Set project: gcloud config set project YOUR_PROJECT_ID"
echo "3. Deploy bots: cd /opt/apps/telegram-bots && ./deploy-bots.sh"
echo "4. Monitor: ./monitor-bots.sh"
echo ""
echo "🔧 Useful commands:"
echo "- systemctl start telegram-bots  # Start bots service"
echo "- systemctl status telegram-bots # Check service status"
echo "- docker compose logs -f         # Follow logs"
echo "- docker compose restart         # Restart all services"