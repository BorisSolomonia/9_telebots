# 🏗️ Deployment Configuration Summary

## 📋 Project Configuration

### Core Infrastructure Settings
```bash
PROJECT_ID="nine-tones-bots-2025-468320"
REGION="us-central1"
ZONE="us-central1-c"
AR_REPO="tasty-ar"
VM_NAME="tasty-tones-1"
VM_IP="35.225.153.97"
APP_NAME="telegram-bot"
SERVICE_NAME="order-bot-secure"
```

### Docker Images & Registry
- **Base Image**: `python:3.11-slim`
- **Registry URL**: `us-central1-docker.pkg.dev/nine-tones-bots-2025-468320/tasty-ar`
- **Image Name**: `telegram-bot`
- **Tags**: `latest`, `{git-sha}`, `{timestamp}`

## 🐳 Container Configuration

### Network Architecture
```yaml
networks:
  web:
    external: true
    driver: bridge
    # Public-facing network for Caddy
  
  bot_internal:
    external: true
    driver: bridge
    internal: true
    # Private network for service communication
```

### Volume Configuration
```yaml
volumes:
  caddy_data:
    external: true
    # SSL certificates and Caddy data
  
  telegram-bot_customer_data:
    external: true
    # Bot customer database
  
  caddy_logs:
    driver: local
    # Caddy access logs
```

### Service Definitions

#### Caddy Reverse Proxy
```yaml
caddy:
  image: caddy:2-alpine
  container_name: caddy-proxy
  restart: unless-stopped
  ports: ["80:80", "443:443"]
  networks: [web, bot_internal]
  resources:
    limits:
      memory: 128M
      cpus: '0.25'
  environment:
    - DOMAIN=${VM_IP}
    - BOT_SERVICE_NAME=order-bot-secure
    - HEALTH_PORT=8080
```

#### Telegram Bot Application
```yaml
order-bot-secure:
  image: us-central1-docker.pkg.dev/nine-tones-bots-2025-468320/tasty-ar/telegram-bot:latest
  container_name: order-bot-secure
  restart: unless-stopped
  networks: [bot_internal]
  user: "1001:1001"
  read_only: true
  resources:
    limits:
      memory: 512M
      cpus: '0.5'
  volumes:
    - telegram-bot_customer_data:/app/data
    - /tmp  # tmpfs for temporary files
```

## 🔐 Secret Manager Configuration

### Required Secrets
```bash
# Core secrets
telegram-bot-token          # From @BotFather
openai-api-key              # From OpenAI Platform
google-service-account-key  # Service account JSON

# Optional configuration
sheet-name                  # Default: "9_ტონა_ფული"
worksheet-name             # Default: "Payments"
```

### Secret Access Pattern
```python
# Runtime secret fetching
TELEGRAM_TOKEN = gcloud_secrets_access("telegram-bot-token")
OPENAI_API_KEY = gcloud_secrets_access("openai-api-key")
GOOGLE_CREDS = gcloud_secrets_access("google-service-account-key")
```

## 🌐 Caddy Routing Configuration

### Health Check Endpoints
```caddyfile
:80 {
  # System health
  handle /health {
    respond "OK" 200
  }
  
  # Caddy health  
  handle /health/caddy {
    respond "Caddy OK" 200
  }
  
  # Bot health (proxied)
  handle /health/bot {
    reverse_proxy order-bot-secure:8080
  }
}
```

### Security Headers
```caddyfile
header {
  X-Content-Type-Options nosniff
  X-Frame-Options DENY
  X-XSS-Protection "1; mode=block"
  Referrer-Policy strict-origin-when-cross-origin
  Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
  -Server
  -X-Powered-By
}
```

### Rate Limiting
```caddyfile
rate_limit {
  zone dynamic {
    key {remote_host}
    events 100
    window 1m
  }
}
```

## 📊 Monitoring & Health Checks

### Container Health Checks
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
  CMD curl -f http://localhost:8080/health || exit 1
```

### Application Metrics
- **Response time tracking**: Request duration histograms
- **Error rate monitoring**: Failed request counters  
- **Resource usage**: Memory and CPU utilization
- **Cache performance**: Hit/miss ratios for GPT cache

### Log Configuration
```python
# Structured JSON logging
logging.config.dictConfig({
    'version': 1,
    'formatters': {
        'json': {
            'format': '{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}'
        }
    },
    'handlers': {
        'stdout': {
            'class': 'logging.StreamHandler',
            'formatter': 'json'
        }
    }
})
```

## 🚀 Deployment Pipeline Configuration

### GitHub Actions Triggers
```yaml
on:
  push:
    branches: [main, master]
    paths:
      - 'improved_order_bot.py'
      - 'config_template.py'
      - 'secure-docker-setup/**'
      - 'infra/**'
      - 'requirements.txt'
  workflow_dispatch:
    inputs:
      force_rebuild: boolean
```

### Deployment Stages
1. **Security Scan** - Trivy vulnerability scanning
2. **Build & Push** - Docker image to Artifact Registry
3. **Deploy Infrastructure** - Upload configs to VM
4. **Deploy Application** - Start containers with health checks
5. **Verification** - Comprehensive health testing
6. **Cleanup** - Remove old images and resources

### Rollback Strategy
```bash
# Automatic rollback triggers
- Health check failures after deployment
- Container startup failures
- Manual rollback via script

# Rollback process
1. Stop current containers
2. Restore previous image version
3. Restore configuration if needed
4. Restart services
5. Verify health checks
```

## 📁 File System Layout

### VM Directory Structure
```
/opt/telegram-bot/
├── .env                           # Runtime environment variables
├── credentials.json               # Google service account
├── infra/
│   └── caddy/
│       ├── compose.yml           # Caddy Docker Compose
│       ├── Caddyfile             # Caddy configuration
│       └── .env                  # Caddy environment
├── secure-docker-setup/
│   ├── docker-compose.secure.yml # Bot Docker Compose
│   └── Dockerfile.secure         # Multi-stage Dockerfile
├── logs/                         # Application logs
└── data/                        # Persistent data (customers.json)
```

### Container Mount Points
```yaml
volumes:
  # Bot container
  - telegram-bot_customer_data:/app/data        # Customer database
  - ./credentials.json:/app/credentials.json:ro # Google credentials
  
  # Caddy container
  - ./Caddyfile:/etc/caddy/Caddyfile:ro        # Caddy config
  - caddy_data:/data                            # SSL certificates
  - caddy_logs:/var/log/caddy                   # Access logs
```

## ⚙️ Environment Variables

### Application Configuration
```bash
# Bot settings
TELEGRAM_TOKEN_BOT=<from-secret-manager>
ORDER_BOT_TOKEN=<from-secret-manager>
OPENAI_API_KEY=<from-secret-manager>

# Google Sheets
SHEET_NAME=9_ტონა_ფული
WORKSHEET_NAME=Payments
CREDS_FILE=/app/credentials.json

# File paths
CUSTOMERS_FILE=/app/data/customers.json

# Performance settings
MESSAGE_COOLDOWN=5
GPT_CACHE_TTL=300
MAX_CACHE_SIZE=1000

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Infrastructure Configuration
```bash
# Docker settings
COMPOSE_PROJECT_NAME=telegram-bot
DOCKER_BUILDKIT=1

# Caddy settings  
DOMAIN=35.225.153.97
BOT_SERVICE_NAME=order-bot-secure
HEALTH_PORT=8080
ACME_EMAIL=admin@example.com
```

## 🔧 Resource Specifications

### Container Resource Limits
```yaml
# Caddy proxy
resources:
  limits:
    memory: 128M
    cpus: '0.25'
  reservations:
    memory: 32M
    cpus: '0.1'

# Telegram bot
resources:
  limits:
    memory: 512M
    cpus: '0.5'
  reservations:
    memory: 128M
    cpus: '0.1'
```

### VM Requirements
- **Instance Type**: e2-medium (2 vCPU, 4GB RAM)
- **Boot Disk**: 20GB SSD
- **Network**: Premium tier with external IP
- **Firewall**: HTTP/HTTPS traffic allowed
- **Service Account**: Compute Engine default with Secret Manager access

## 🔄 Update & Maintenance Procedures

### Automated Updates (GitHub Actions)
1. Code changes pushed to main branch
2. Security scan and build triggered
3. New image pushed to Artifact Registry  
4. Zero-downtime deployment to VM
5. Health checks verify deployment
6. Old images cleaned up automatically

### Manual Updates
```bash
# Update application
./deploy-to-tasty-tones.sh deploy

# Update secrets
echo "new_value" | gcloud secrets versions add secret-name --data-file=-
./deploy-to-tasty-tones.sh deploy  # Restart with new secrets

# Update configuration
# Edit files, then:
./deploy-to-tasty-tones.sh deploy
```

### Backup Procedures
```bash
# Backup customer data
docker run --rm --volumes-from order-bot-secure \
  -v /tmp:/backup alpine \
  tar czf /backup/customers-$(date +%Y%m%d).tar.gz /app/data

# Backup secrets (emergency only)
gcloud secrets versions access latest --secret=telegram-bot-token > backup.txt
```

This configuration provides a production-ready, secure, and maintainable Telegram bot deployment with comprehensive monitoring, automated updates, and rollback capabilities.