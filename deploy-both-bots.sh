#!/bin/bash

# Deploy both bots with shared customers.json
# For VM: tasty-tones-1

set -euo pipefail

echo "🤖 Deploying both Order Bot and Payment Bot..."

# Configuration
PROJECT_ID="nine-tones-bots-2025-468320"
VM_NAME="tasty-tones-1"
ZONE="us-central1-c"
APP_DIR="/opt/app1"

# Stop current single bot
echo "⏹️ Stopping current single bot..."
gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command="
cd $APP_DIR/secure-docker-setup
docker-compose -f docker-compose.secure.yml down || true
"

# Upload multi-bot configuration
echo "📤 Uploading multi-bot configuration..."
gcloud compute scp multi-bot-compose.yml "${VM_NAME}:${APP_DIR}/multi-bot-compose.yml" --zone="$ZONE" --project="$PROJECT_ID"

# Deploy both bots
echo "🚀 Starting both bots..."
gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command="
cd $APP_DIR

# Create .env with both tokens from Secret Manager
echo 'Fetching secrets from Secret Manager...'
{
  echo \"ORDER_BOT_TOKEN=\$(gcloud secrets versions access latest --secret=telegram-bot-token --project=${PROJECT_ID} 2>/dev/null || echo 'MISSING')\"
  echo \"TELEGRAM_TOKEN_BOT=\$(gcloud secrets versions access latest --secret=payment-bot-token --project=${PROJECT_ID} 2>/dev/null || echo 'MISSING')\"
  echo \"PAYMENT_BOT_TOKEN=\$(gcloud secrets versions access latest --secret=payment-bot-token --project=${PROJECT_ID} 2>/dev/null || echo 'MISSING')\"
  echo \"OPENAI_API_KEY=\$(gcloud secrets versions access latest --secret=openai-api-key --project=${PROJECT_ID} 2>/dev/null || echo 'MISSING')\"
  echo \"SHEET_NAME=\$(gcloud secrets versions access latest --secret=sheet-name --project=${PROJECT_ID} 2>/dev/null || echo '9_ტონა_ფული')\"
  echo \"WORKSHEET_NAME_ORDERS=orders\"
  echo \"WORKSHEET_NAME_PAYMENTS=Payments\"
  echo \"REDIS_PASSWORD=secure_redis_pass_\$(openssl rand -hex 8)\"
} > .env.template

# Expand variables
eval \"\$(cat .env.template)\" && env | grep -E '^(ORDER_|TELEGRAM_|PAYMENT_|OPENAI_|SHEET_|WORKSHEET_|REDIS_)' > .env

# Initialize shared customers.json in volume
echo 'Setting up shared customers.json...'
docker volume create multi-bot-compose_shared_customer_data 2>/dev/null || true

# Copy existing customers.json to shared volume
if [ -f 'secure-docker-setup/customers.json' ]; then
  docker run --rm \\
    -v multi-bot-compose_shared_customer_data:/data \\
    -v \$(pwd)/secure-docker-setup:/host:ro \\
    alpine cp /host/customers.json /data/customers.json
  echo '✅ Copied existing customers.json to shared volume'
else
  echo '[]' | docker run --rm -i \\
    -v multi-bot-compose_shared_customer_data:/data \\
    alpine tee /data/customers.json
  echo '✅ Created empty customers.json in shared volume'  
fi

# Start both bots
echo '🤖 Starting both bots...'
docker-compose -f multi-bot-compose.yml up -d

echo '✅ Both bots started!'
sleep 10

# Show status
echo '🔍 Bot status:'
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo ''
echo '📋 Bot logs (last 10 lines each):'
echo '--- Order Bot ---'
docker logs order-bot-secure --tail 10 2>/dev/null || echo 'No order bot logs yet'
echo '--- Payment Bot ---'  
docker logs payment-bot-secure --tail 10 2>/dev/null || echo 'No payment bot logs yet'
"

echo ""
echo "🎉 Deployment completed!"
echo ""
echo "📍 Access points:"
echo "   Order Bot health: http://35.225.153.97:8081/health"  
echo "   Payment Bot health: http://35.225.153.97:8082/health"
echo ""
echo "📊 To monitor:"
echo "   gcloud compute ssh $VM_NAME --zone=$ZONE --command='docker logs order-bot-secure'"
echo "   gcloud compute ssh $VM_NAME --zone=$ZONE --command='docker logs payment-bot-secure'"