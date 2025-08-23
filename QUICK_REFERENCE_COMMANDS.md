# ⚡ Quick Reference Commands

## 🚀 Essential Deployment Commands

### One-Time Setup
```bash
# Setup secrets in Secret Manager (interactive)
chmod +x quick-secrets-setup.sh
./quick-secrets-setup.sh

# Complete deployment
chmod +x deploy-to-tasty-tones.sh
./deploy-to-tasty-tones.sh
```

### Daily Operations
```bash
# Deploy/update the bot
./deploy-to-tasty-tones.sh deploy

# Check system status
./deploy-to-tasty-tones.sh status

# View bot logs
./deploy-to-tasty-tones.sh logs

# Health checks
./deploy-to-tasty-tones.sh health

# Rollback if needed
./deploy-to-tasty-tones.sh rollback
```

## 🔧 Infrastructure Management

### GCP Commands
```bash
# Set your project
gcloud config set project nine-tones-bots-2025-468320

# Connect to VM
gcloud compute ssh tasty-tones-1 --zone=us-central1-c

# Check VM status
gcloud compute instances describe tasty-tones-1 --zone=us-central1-c

# List running instances
gcloud compute instances list
```

### Docker Commands (on VM)
```bash
# Connect to VM first
gcloud compute ssh tasty-tones-1 --zone=us-central1-c

# Container status
docker ps

# View logs
docker logs order-bot-secure
docker logs caddy-proxy

# Resource usage
docker stats

# Restart services
cd /opt/telegram-bot
docker-compose -f secure-docker-setup/docker-compose.secure.yml restart

# Update and redeploy
docker-compose -f secure-docker-setup/docker-compose.secure.yml pull
docker-compose -f secure-docker-setup/docker-compose.secure.yml up -d
```

## 🔐 Secret Management

### View Secrets
```bash
# List all secrets
gcloud secrets list

# View specific secret (will show actual value!)
gcloud secrets versions access latest --secret=telegram-bot-token

# Check secret exists without showing value
gcloud secrets describe telegram-bot-token
```

### Update Secrets
```bash
# Update bot token
echo "NEW_TOKEN" | gcloud secrets versions add telegram-bot-token --data-file=-

# Update OpenAI key
echo "NEW_API_KEY" | gcloud secrets versions add openai-api-key --data-file=-

# Update Google service account
gcloud secrets versions add google-service-account-key --data-file=new-credentials.json

# After updating secrets, restart bot
./deploy-to-tasty-tones.sh deploy
```

## 🌐 Health & Monitoring

### Quick Health Checks
```bash
# External health check
curl http://35.225.153.97/health

# Comprehensive health
curl -v http://35.225.153.97/health/bot
curl -v http://35.225.153.97/health/caddy

# From inside VM
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  curl http://localhost/health &&
  curl http://localhost/health/bot &&
  curl http://localhost/health/caddy
"
```

### Monitor Resources
```bash
# VM resource usage
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  echo '=== CPU and Memory ==='
  top -bn1 | head -20
  echo '=== Disk Usage ==='
  df -h
  echo '=== Docker Stats ==='
  docker stats --no-stream
"
```

### Check Logs
```bash
# Bot application logs
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker logs order-bot-secure --tail 50"

# Caddy proxy logs  
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker logs caddy-proxy --tail 50"

# System logs
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="journalctl -u docker --lines 20"

# Search for errors
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker logs order-bot-secure 2>&1 | grep -i error"
```

## 🔄 Troubleshooting Commands

### Container Issues
```bash
# Connect to VM
gcloud compute ssh tasty-tones-1 --zone=us-central1-c

# Check container status
docker ps -a

# Inspect failed container
docker inspect order-bot-secure

# Check container health
docker exec order-bot-secure curl -f http://localhost:8080/health

# Restart specific container
docker restart order-bot-secure

# Rebuild and restart
cd /opt/telegram-bot
docker-compose -f secure-docker-setup/docker-compose.secure.yml down
docker-compose -f secure-docker-setup/docker-compose.secure.yml up -d
```

### Network Issues
```bash
# Check Docker networks
docker network ls
docker network inspect web
docker network inspect bot_internal

# Test connectivity
docker exec caddy-proxy ping order-bot-secure
docker exec order-bot-secure curl http://caddy-proxy

# Check ports
netstat -tlnp | grep -E "80|443|8080"
```

### Configuration Issues
```bash
# Check environment variables (on VM)
cd /opt/telegram-bot
cat .env | grep -v TOKEN | grep -v API_KEY  # Don't show sensitive values

# Validate Caddy config
docker exec caddy-proxy caddy validate --config /etc/caddy/Caddyfile

# Check file permissions
ls -la /opt/telegram-bot/
docker exec order-bot-secure ls -la /app/
```

## 📦 Development Commands

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run bot locally (need .env file)
python improved_order_bot.py

# Run with original bot
python order_bot.py

# Test configuration
python config_template.py
```

### Docker Development
```bash
# Build image locally
docker build -f secure-docker-setup/Dockerfile.secure -t telegram-bot:dev .

# Run locally with docker-compose
docker-compose -f secure-docker-setup/docker-compose.secure.yml up -d

# View logs
docker-compose -f secure-docker-setup/docker-compose.secure.yml logs -f
```

## 🎯 Common Workflows

### New Deployment
```bash
# 1. First time setup
./quick-secrets-setup.sh

# 2. Deploy
./deploy-to-tasty-tones.sh

# 3. Verify
curl http://35.225.153.97/health
```

### Update Bot Code
```bash
# 1. Make changes to improved_order_bot.py

# 2. Deploy changes
./deploy-to-tasty-tones.sh deploy

# 3. Check logs for issues
./deploy-to-tasty-tones.sh logs
```

### Update Secrets
```bash
# 1. Update secret in Secret Manager
echo "new_value" | gcloud secrets versions add secret-name --data-file=-

# 2. Restart bot to pick up new secret
./deploy-to-tasty-tones.sh deploy

# 3. Verify functionality
./deploy-to-tasty-tones.sh health
```

### Emergency Recovery
```bash
# 1. Check what's wrong
./deploy-to-tasty-tones.sh status
./deploy-to-tasty-tones.sh health

# 2. If services are down, restart
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  cd /opt/telegram-bot
  docker-compose -f secure-docker-setup/docker-compose.secure.yml restart
"

# 3. If still failing, full redeploy
./deploy-to-tasty-tones.sh deploy

# 4. If critically broken, rollback
./deploy-to-tasty-tones.sh rollback
```

## 📊 Monitoring Commands

### Performance Monitoring
```bash
# Real-time resource usage
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker stats"

# Disk usage
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  echo 'System disk usage:'
  df -h
  echo 'Docker disk usage:'  
  docker system df
"

# Memory details
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  free -h
  docker exec order-bot-secure cat /proc/meminfo | head -10
"
```

### Log Monitoring
```bash
# Follow logs in real-time
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker logs order-bot-secure -f"

# Search logs for patterns
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker logs order-bot-secure 2>&1 | grep -E '(ERROR|WARNING|order_processed)'
"

# Get logs from specific time
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker logs order-bot-secure --since='1h'
"
```

## 🚨 Emergency Commands

### Critical Issues
```bash
# EMERGENCY: Stop everything
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker stop \$(docker ps -q)
"

# EMERGENCY: Start essential services only
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  cd /opt/telegram-bot/infra/caddy && docker-compose up -d
  cd /opt/telegram-bot && docker-compose -f secure-docker-setup/docker-compose.secure.yml up -d order-bot-secure
"

# EMERGENCY: Complete system restart
gcloud compute instances stop tasty-tones-1 --zone=us-central1-c
gcloud compute instances start tasty-tones-1 --zone=us-central1-c
```

### Token Compromised
```bash
# 1. Immediately revoke token via @BotFather
# 2. Generate new token
# 3. Update secret
echo "NEW_TOKEN" | gcloud secrets versions add telegram-bot-token --data-file=-
# 4. Restart bot
./deploy-to-tasty-tones.sh deploy
```

## 💾 Backup & Recovery

### Create Backup
```bash
# Backup customer data
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker run --rm --volumes-from order-bot-secure -v /tmp:/backup alpine \
  tar czf /backup/customers-backup-\$(date +%Y%m%d-%H%M).tar.gz /app/data
"

# Download backup
gcloud compute scp tasty-tones-1:/tmp/customers-backup-*.tar.gz . --zone=us-central1-c
```

### Restore from Backup
```bash
# Upload backup file
gcloud compute scp customers-backup-*.tar.gz tasty-tones-1:/tmp/ --zone=us-central1-c

# Restore data
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker run --rm -v telegram-bot_customer_data:/app/data -v /tmp:/backup alpine \
  tar xzf /backup/customers-backup-*.tar.gz -C /
"
```

## 🔍 Debug Commands

### Deep Debugging
```bash
# Enter bot container
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker exec -it order-bot-secure /bin/bash"

# Check environment inside container
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker exec order-bot-secure env | grep -E '(TOKEN|API|SHEET)'"

# Check file system
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker exec order-bot-secure ls -la /app/"

# Test Python imports
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker exec order-bot-secure python -c 'import telegram; import openai; print(\"Imports OK\")'"
```

### Network Debugging
```bash
# Test external connectivity
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker exec order-bot-secure curl -I https://api.telegram.org
  docker exec order-bot-secure curl -I https://api.openai.com
"

# Check DNS resolution
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker exec order-bot-secure nslookup api.telegram.org
  docker exec order-bot-secure nslookup api.openai.com
"
```

---

## 📝 Notes

- Always use `gcloud config set project nine-tones-bots-2025-468320` before GCP commands
- VM IP `35.225.153.97` is your main access point
- Bot container name is always `order-bot-secure`
- Caddy container name is always `caddy-proxy`
- All secrets are stored in GCP Secret Manager
- Health endpoints: `/health`, `/health/bot`, `/health/caddy`

**💡 Pro tip:** Bookmark this file for quick access to commands!