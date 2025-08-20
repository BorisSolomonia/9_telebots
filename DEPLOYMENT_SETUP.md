# 🚀 Telegram Bots Deployment Setup Guide

This guide follows the architecture from `DEPLOY.md` and provides step-by-step instructions for deploying the 9-Tones Telegram bots.

## 📋 Prerequisites

- Google Cloud Platform account
- GitHub repository with this code
- Domain name (optional, for custom domain)

## 🏗️ Architecture Overview

```
GitHub Actions → GCP Artifact Registry → GCP VM
├── Docker Images (telegram-bots:latest)
├── Caddy Reverse Proxy (:80, :443)
├── Payment Bot (telegram polling)
└── Order Bot (telegram polling)
```

## 🛠️ Step 1: GCP Setup

### 1.1 Create GCP Project
```bash
export PROJECT_ID="your-telegram-bots-project"
gcloud projects create $PROJECT_ID
gcloud config set project $PROJECT_ID
```

### 1.2 Enable APIs
```bash
gcloud services enable compute.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable secretmanager.googleapis.com
```

### 1.3 Create Artifact Registry
```bash
gcloud artifacts repositories create apps \
  --repository-format=docker \
  --location=europe-west3 \
  --description="Telegram bots containers"
```

### 1.4 Create VM Instance
```bash
gcloud compute instances create telegram-bots-vm \
  --zone=europe-west3-a \
  --machine-type=e2-medium \
  --boot-disk-size=20GB \
  --boot-disk-type=pd-standard \
  --image-family=ubuntu-2004-lts \
  --image-project=ubuntu-os-cloud \
  --tags=http-server,https-server \
  --metadata-from-file startup-script=vm-startup.sh
```

## 🔐 Step 2: Secret Manager Setup

### 2.1 Run Setup Script
```bash
chmod +x secrets-setup.sh
./secrets-setup.sh
```

This will create:
- `telegram-bots-env` - Main environment file
- `telegram-payment-bot-token` - Payment bot token
- `telegram-order-bot-token` - Order bot token  
- `openai-api-key` - OpenAI API key
- `sheets-credentials` - Google Sheets service account
- `customers-data` - Customer data JSON

### 2.2 Manual Secret Updates
```bash
# Update environment variables
gcloud secrets versions add telegram-bots-env --data-file=.env.production

# Update specific secrets
echo "new-bot-token" | gcloud secrets create telegram-payment-bot-token --data-file=-
```

## 🔑 Step 3: GitHub Secrets Configuration

Add these secrets to your GitHub repository:

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `GCP_PROJECT_ID` | Your GCP project ID | `telegram-bots-2025` |
| `GCP_SA_KEY` | Service account key JSON | `{"type": "service_account"...}` |
| `VM_HOST` | VM external IP address | `34.141.45.73` |
| `VM_SSH_USER` | VM SSH username | `your-username` |
| `VM_SSH_KEY` | VM SSH private key | `-----BEGIN OPENSSH PRIVATE KEY-----` |

## 🚀 Step 4: Deploy

### 4.1 Automatic Deployment
Push to master branch or trigger manual workflow:
```bash
git push origin master
```

### 4.2 Manual Deployment on VM
```bash
# SSH into VM
gcloud compute ssh telegram-bots-vm --zone=europe-west3-a

# Run deployment script
cd /opt/apps/telegram-bots
./deploy-bots.sh
```

## 📊 Step 5: Monitoring

### 5.1 Check Deployment Status
```bash
# On VM
./monitor-bots.sh

# Or check individual services
docker compose ps
docker compose logs -f
```

### 5.2 Health Checks
```bash
# Test health endpoint
curl http://VM_IP/health

# Test bot status
curl http://VM_IP/bots/payment/status
curl http://VM_IP/bots/order/status
```

### 5.3 System Service Status
```bash
# Check systemd service
systemctl status telegram-bots

# Start/stop service
systemctl start telegram-bots
systemctl stop telegram-bots
```

## 🔧 Step 6: Configuration Updates

### 6.1 Update Bot Configuration
```bash
# Update .env.production locally
# Then update secret
gcloud secrets versions add telegram-bots-env --data-file=.env.production

# Redeploy
cd /opt/apps/telegram-bots
./deploy-bots.sh
```

### 6.2 Scale Resources
```bash
# Stop VM
gcloud compute instances stop telegram-bots-vm --zone=europe-west3-a

# Change machine type
gcloud compute instances set-machine-type telegram-bots-vm \
  --machine-type=e2-standard-2 \
  --zone=europe-west3-a

# Start VM
gcloud compute instances start telegram-bots-vm --zone=europe-west3-a
```

## 🐛 Troubleshooting

### Common Issues

#### 1. Bot Not Responding
```bash
# Check bot logs
docker compose logs payment-bot
docker compose logs order-bot

# Check bot tokens
gcloud secrets versions access latest --secret=telegram-payment-bot-token
```

#### 2. Secrets Access Issues
```bash
# Check service account permissions
gcloud projects get-iam-policy $PROJECT_ID

# Test secret access
gcloud secrets versions access latest --secret=telegram-bots-env
```

#### 3. Container Health Issues
```bash
# Check container status
docker compose ps

# Restart specific service
docker compose restart payment-bot

# View detailed logs
docker compose logs --tail=50 payment-bot
```

#### 4. Network Issues
```bash
# Check firewall rules
gcloud compute firewall-rules list

# Test connectivity
curl -v http://localhost/health
```

### Log Locations
- Application logs: `/opt/apps/telegram-bots/logs/`
- System logs: `/var/log/telegram-bots-monitor.log`
- Docker logs: `docker compose logs`

## 📈 Performance Optimization

### Resource Monitoring
```bash
# Check resource usage
htop
docker stats

# Monitor disk usage
df -h
du -sh /opt/apps/telegram-bots/
```

### Log Rotation
Logs are automatically rotated daily and kept for 14 days via logrotate configuration.

## 🔒 Security Best Practices

1. **Secrets Management**: All sensitive data in Secret Manager
2. **Non-root Containers**: Bots run as non-root user (botuser:1001)
3. **Network Security**: Caddy handles all external traffic
4. **Firewall**: Only ports 80, 443, and SSH allowed
5. **Updates**: Regular system and container updates

## 📚 Additional Resources

- [DEPLOY.md](./DEPLOY.md) - Complete deployment architecture guide
- [Google Cloud Secret Manager](https://cloud.google.com/secret-manager/docs)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Caddy Documentation](https://caddyserver.com/docs/)

---

✅ **Deployment Complete!** Your Telegram bots are now running with production-grade infrastructure following the 9-Tones architecture pattern.