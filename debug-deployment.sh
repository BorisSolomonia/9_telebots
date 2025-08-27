#!/bin/bash

# Comprehensive deployment debugging script
# Run this on your VM to diagnose bot issues

set -e

echo "🔍 TELEGRAM BOT DEPLOYMENT DIAGNOSTICS"
echo "======================================"

APP_NAME="app1"  # Change this to match your app
APP_DIR="/opt/$APP_NAME"

echo "📊 1. CONTAINER STATUS CHECK"
echo "----------------------------"
echo "All containers:"
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}'

echo ""
echo "Bot containers specifically:"
docker ps -a | grep -E "(order-bot|telegram|bot)" || echo "No bot containers found"

echo ""
echo "📋 2. RECENT CONTAINER LOGS"
echo "---------------------------"
echo "=== order-bot-secure logs (last 50 lines) ==="
docker logs order-bot-secure --tail 50 2>&1 || echo "Failed to get order-bot-secure logs"

echo ""
echo "=== bot-redis logs (last 20 lines) ==="
docker logs bot-redis --tail 20 2>&1 || echo "Failed to get redis logs"

echo ""
echo "📁 3. FILE SYSTEM CHECK"
echo "-----------------------"
cd "$APP_DIR" || { echo "❌ Cannot access $APP_DIR"; exit 1; }
echo "Current directory: $(pwd)"
echo ""
echo "Files in app directory:"
ls -la .

echo ""
echo "Files in secure-docker-setup:"
ls -la secure-docker-setup/ || echo "secure-docker-setup directory not found"

echo ""
echo "Environment file check:"
if [ -f "secure-docker-setup/.env" ]; then
    echo "✅ .env file exists"
    echo "Size: $(wc -l secure-docker-setup/.env)"
    echo "First few variables (without values):"
    grep -E "^[A-Z_]+" secure-docker-setup/.env | cut -d= -f1 | head -10
else
    echo "❌ .env file missing"
fi

echo ""
echo "🐳 4. DOCKER COMPOSE STATUS"
echo "---------------------------"
cd secure-docker-setup
echo "Docker compose config validation:"
if docker compose -f docker-compose.secure.yml config --quiet; then
    echo "✅ Compose file is valid"
else
    echo "❌ Compose file has errors"
    docker compose -f docker-compose.secure.yml config 2>&1 || true
fi

echo ""
echo "Services defined in compose:"
docker compose -f docker-compose.secure.yml config --services 2>/dev/null || echo "Failed to get services"

echo ""
echo "🌐 5. NETWORK CONNECTIVITY"
echo "--------------------------"
echo "Docker networks:"
docker network ls | grep -E "(bot|web|bridge)" || echo "No relevant networks found"

echo ""
echo "Container network info:"
docker inspect order-bot-secure --format '{{.NetworkSettings.Networks}}' 2>/dev/null || echo "Cannot inspect container networks"

echo ""
echo "🔧 6. ENVIRONMENT VARIABLES IN CONTAINER"
echo "----------------------------------------"
echo "Environment variables in running container:"
docker exec order-bot-secure env 2>/dev/null | head -20 || echo "Cannot access container environment"

echo ""
echo "🌍 7. EXTERNAL CONNECTIVITY TEST"
echo "--------------------------------"
echo "Testing internet connectivity from container:"
docker exec order-bot-secure ping -c 2 8.8.8.8 2>/dev/null || echo "No internet connectivity or container not running"

echo ""
echo "Testing Telegram API connectivity:"
docker exec order-bot-secure curl -s --connect-timeout 5 https://api.telegram.org/bot 2>/dev/null && echo "✅ Can reach Telegram API" || echo "❌ Cannot reach Telegram API"

echo ""
echo "🚨 8. CONTAINER HEALTH CHECK"
echo "----------------------------"
echo "Container inspect (health and status):"
docker inspect order-bot-secure --format '{{.State.Status}} - {{.State.Health.Status}} - RestartCount: {{.RestartCount}}' 2>/dev/null || echo "Cannot inspect container"

echo ""
echo "Recent container events:"
docker events --since 5m --filter container=order-bot-secure 2>/dev/null &
sleep 2
kill %1 2>/dev/null || true

echo ""
echo "📱 9. TELEGRAM BOT SPECIFIC CHECKS"
echo "----------------------------------"
if [ -f "../.env" ] || [ -f ".env" ]; then
    echo "Attempting to extract bot token for testing..."
    
    # Try to get token from .env file
    TOKEN=$(grep -E "^(TELEGRAM_TOKEN_BOT|ORDER_BOT_TOKEN)" .env 2>/dev/null | head -1 | cut -d= -f2 | tr -d '"'"'" || echo "")
    
    if [ -n "$TOKEN" ]; then
        echo "✅ Found bot token"
        echo "Testing bot getMe API call:"
        curl -s "https://api.telegram.org/bot$TOKEN/getMe" | head -100 || echo "Failed to call Telegram API"
    else
        echo "❌ No bot token found in .env"
    fi
else
    echo "❌ No .env file found for token extraction"
fi

echo ""
echo "🏁 DIAGNOSIS SUMMARY"
echo "==================="
echo "1. Check the container logs above for Python errors"
echo "2. Verify environment variables are loaded correctly"
echo "3. Confirm network connectivity to Telegram API"
echo "4. Check if bot token is valid and bot is not blocked"
echo ""
echo "Common issues:"
echo "- Python import errors or missing dependencies"
echo "- Invalid or revoked bot token"  
echo "- Network connectivity issues"
echo "- Missing environment variables"
echo "- Port binding conflicts"
echo ""
echo "Next steps:"
echo "1. If container keeps restarting, check logs for Python errors"
echo "2. If no errors but bot doesn't respond, test token manually"
echo "3. If API calls fail, check network/firewall settings"