# 🔧 Troubleshooting Guide

## 🚨 Emergency Procedures

### CRITICAL: Bot Token Compromised
If you suspect the bot token has been compromised:

```bash
# 1. IMMEDIATELY revoke the token
# Go to @BotFather on Telegram:
# /mybots → Select Bot → Bot Settings → Revoke Token!!!

# 2. Generate new token
# /mybots → Select Bot → Bot Settings → Generate New Token!!!

# 3. Update secret in Secret Manager
echo "NEW_TOKEN_HERE" | gcloud secrets versions add telegram-bot-token --data-file=-

# 4. Restart the bot
./deploy-to-tasty-tones.sh deploy
```

### Service Down Emergency
```bash
# Quick health check
curl -f http://35.225.153.97/health

# If down, check container status
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker ps"

# Emergency restart
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  cd /opt/telegram-bot
  docker-compose -f secure-docker-setup/docker-compose.secure.yml restart
"
```

## 🔍 Common Issues & Solutions

### 1. Container Won't Start

**Symptoms:**
- Container status shows "Exited" or "Restarting"
- Health checks fail immediately

**Diagnosis:**
```bash
# Check container logs
./deploy-to-tasty-tones.sh logs

# Check container status
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker ps -a"

# Check specific container
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker logs order-bot-secure"
```

**Common Causes & Fixes:**

#### Missing or Invalid Secrets
```bash
# Check if secrets exist
gcloud secrets list --filter="name:telegram-bot OR name:openai"

# Test secret access
gcloud secrets versions access latest --secret=telegram-bot-token

# Recreate missing secrets
./quick-secrets-setup.sh
```

#### Invalid Environment Variables
```bash
# Check environment file on VM
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  cd /opt/telegram-bot
  cat .env | grep -v 'API_KEY\|TOKEN'  # Don't show sensitive values
"

# Regenerate environment
./deploy-to-tasty-tones.sh deploy
```

#### Permission Issues
```bash
# Check file permissions
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  ls -la /opt/telegram-bot/
  docker exec order-bot-secure ls -la /app/
"

# Fix permissions (if needed)
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  sudo chown -R 1001:1001 /opt/telegram-bot/data/
"
```

### 2. Health Checks Failing

**Symptoms:**
- `/health` endpoint returns 404 or 500
- Container marked as unhealthy

**Diagnosis:**
```bash
# Test health endpoints directly
curl -v http://35.225.153.97/health
curl -v http://35.225.153.97/health/bot
curl -v http://35.225.153.97/health/caddy

# Check from inside VM
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  curl -v http://localhost/health
  curl -v http://localhost:8080/health
"
```

**Common Fixes:**

#### Caddy Configuration Issues
```bash
# Check Caddy config syntax
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker exec caddy-proxy caddy validate --config /etc/caddy/Caddyfile
"

# Check Caddy logs
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker logs caddy-proxy --tail 20
"

# Restart Caddy if needed
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  cd /opt/telegram-bot/infra/caddy
  docker-compose restart
"
```

#### Bot Application Not Responding
```bash
# Check if bot is listening on port 8080
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker exec order-bot-secure netstat -tlnp | grep 8080
"

# Check bot internal health
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker exec order-bot-secure curl -f http://localhost:8080/health
"
```

### 3. Network Connectivity Issues

**Symptoms:**
- External access fails
- Bot can't reach external APIs

**Diagnosis:**
```bash
# Check firewall rules
gcloud compute firewall-rules list --filter="name:telegram-bot OR name:http"

# Test external connectivity from VM
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  curl -I https://api.telegram.org
  curl -I https://api.openai.com
"

# Check Docker networks
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker network ls
  docker network inspect web
  docker network inspect bot_internal
"
```

**Fixes:**

#### Create Missing Firewall Rules
```bash
gcloud compute firewall-rules create allow-telegram-bot-http \
  --allow tcp:80,tcp:443 \
  --source-ranges 0.0.0.0/0 \
  --target-tags http-server \
  --project=nine-tones-bots-2025-468320
```

#### Recreate Docker Networks
```bash
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker network create web 2>/dev/null || true
  docker network create bot_internal --internal 2>/dev/null || true
"
```

### 4. OpenAI API Issues

**Symptoms:**
- Bot responds with "ვერ მოხერხდა შეკვეთის ამოცნობა"
- Logs show OpenAI API errors

**Diagnosis:**
```bash
# Check OpenAI API key
gcloud secrets versions access latest --secret=openai-api-key | head -c 10

# Check API usage/quota
# (Check your OpenAI dashboard)

# Test API key manually
curl -H "Authorization: Bearer $(gcloud secrets versions access latest --secret=openai-api-key)" \
  https://api.openai.com/v1/models | jq '.data[0].id'
```

**Common Fixes:**

#### API Key Issues
```bash
# Update API key
echo "NEW_OPENAI_API_KEY" | gcloud secrets versions add openai-api-key --data-file=-
./deploy-to-tasty-tones.sh deploy
```

#### Rate Limiting
- Check OpenAI dashboard for rate limits
- Consider upgrading OpenAI plan
- Implement request throttling in bot

#### API Quota Exceeded
- Check OpenAI billing dashboard
- Add payment method or increase limits

### 5. Google Sheets Integration Issues

**Symptoms:**
- Orders parsed but not recorded to sheets
- Google API authentication errors

**Diagnosis:**
```bash
# Check service account key
gcloud secrets versions access latest --secret=google-service-account-key | jq '.type'

# Test sheets access (on VM)
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker exec order-bot-secure python -c '
import gspread
from oauth2client.service_account import ServiceAccountCredentials
creds = ServiceAccountCredentials.from_json_keyfile_name(\"/app/credentials.json\", [\"\"])
print(\"Credentials loaded successfully\")
'
"
```

**Common Fixes:**

#### Service Account Issues
```bash
# Verify service account has proper permissions:
# 1. Go to Google Cloud Console → IAM
# 2. Check service account has these roles:
#    - Editor or specific Sheets API access
# 3. Enable Google Sheets API if not enabled

gcloud services enable sheets.googleapis.com --project=nine-tones-bots-2025-468320
```

#### Sheet Access Issues
```bash
# Check if sheet exists and is accessible
# 1. Share the Google Sheet with the service account email
# 2. Check sheet name matches the configuration
# 3. Verify worksheet name exists

# Update sheet configuration
echo "CORRECT_SHEET_NAME" | gcloud secrets versions add sheet-name --data-file=-
./deploy-to-tasty-tones.sh deploy
```

## 🔄 Recovery Procedures

### Complete System Recovery

If everything is broken and you need to start fresh:

```bash
# 1. Stop all services
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker stop \$(docker ps -q) 2>/dev/null || true
  docker system prune -f
"

# 2. Redeploy from scratch
./deploy-to-tasty-tones.sh deploy

# 3. If still failing, check secrets
./quick-secrets-setup.sh

# 4. Deploy again
./deploy-to-tasty-tones.sh deploy
```

### Data Recovery

#### Customer Data Recovery
```bash
# Check if customer data exists
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker exec order-bot-secure cat /app/data/customers.json | jq length
"

# If missing, restore from backup or recreate
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker exec order-bot-secure sh -c 'echo \"[]\" > /app/data/customers.json'
"
```

#### Container Data Recovery
```bash
# List available backups
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  ls -la /tmp/backup/ 2>/dev/null || echo 'No backups found'
"

# Restore from backup (if available)
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker run --rm -v telegram-bot_customer_data:/app/data -v /tmp/backup:/backup alpine \
  tar xzf /backup/customers-YYYYMMDD.tar.gz -C /
"
```

## 📊 Monitoring & Diagnostics

### Performance Monitoring
```bash
# Check resource usage
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker stats --no-stream
"

# Check disk usage
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  df -h
  docker system df
"

# Check memory usage
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  free -h
  docker exec order-bot-secure cat /proc/meminfo | head -5
"
```

### Log Analysis
```bash
# Get comprehensive logs
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  echo '=== CADDY LOGS ==='
  docker logs caddy-proxy --tail 50
  echo '=== BOT LOGS ==='
  docker logs order-bot-secure --tail 50
  echo '=== SYSTEM LOGS ==='
  journalctl -u docker --lines 20
"

# Search for specific errors
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker logs order-bot-secure 2>&1 | grep -i error | tail -10
"
```

### Network Diagnostics
```bash
# Check port connectivity
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  netstat -tlnp | grep -E '80|443|8080'
"

# Test internal communication
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker exec caddy-proxy nslookup order-bot-secure
  docker exec order-bot-secure nslookup caddy-proxy
"
```

## 🆘 Getting Help

### Gathering Information for Support
When reporting issues, collect this information:

```bash
# System information
echo "=== SYSTEM INFO ==="
gcloud compute instances describe tasty-tones-1 --zone=us-central1-c --format="value(status,machineType)"

# Container status
echo "=== CONTAINER STATUS ==="
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker ps -a"

# Recent logs
echo "=== RECENT LOGS ==="
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker logs order-bot-secure --tail 20"

# Configuration (sanitized)
echo "=== CONFIGURATION ==="
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  cd /opt/telegram-bot
  ls -la
  cat .env | sed 's/=.*/=***REDACTED***/' 2>/dev/null || echo 'No .env file'
"
```

### Support Checklist
Before asking for help:

- [ ] Checked container logs with `./deploy-to-tasty-tones.sh logs`
- [ ] Verified health endpoints are accessible
- [ ] Confirmed secrets are properly set in Secret Manager
- [ ] Tested basic network connectivity
- [ ] Reviewed recent changes or deployments
- [ ] Checked resource usage and limits
- [ ] Attempted basic troubleshooting steps above

### Emergency Contacts & Resources
- **Telegram Bot API Documentation**: https://core.telegram.org/bots/api
- **OpenAI API Documentation**: https://platform.openai.com/docs
- **Google Sheets API**: https://developers.google.com/sheets/api
- **Docker Documentation**: https://docs.docker.com/
- **Caddy Documentation**: https://caddyserver.com/docs/

Remember: Most issues can be resolved by redeploying with `./deploy-to-tasty-tones.sh deploy` after verifying the secrets and configuration are correct.