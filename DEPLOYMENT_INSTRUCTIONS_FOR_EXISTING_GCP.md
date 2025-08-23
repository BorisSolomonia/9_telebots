# 🚀 Deployment Instructions for Existing GCP Infrastructure

## Your Current Setup
- **Project ID**: `nine-tones-bots-2025-468320`
- **Region**: `us-central1`
- **Zone**: `us-central1-c`
- **VM**: `tasty-tones-1` (IP: `35.225.153.97`)
- **Artifact Registry**: `tasty-ar`

## 🎯 Quick Deployment (Recommended)

### Option 1: Automated Script Deployment

```bash
# Make scripts executable
chmod +x quick-secrets-setup.sh
chmod +x deploy-to-tasty-tones.sh

# 1. Setup secrets (run once)
./quick-secrets-setup.sh

# 2. Deploy the bot
./deploy-to-tasty-tones.sh
```

### Option 2: GitHub Actions Deployment

1. **Add GitHub Secrets** (Settings > Secrets and Variables > Actions):
   - `GCP_SA_KEY`: Your service account JSON key content

2. **Push to GitHub**:
   ```bash
   git add .
   git commit -m "Add production deployment configuration"
   git push origin main
   ```

3. **Monitor** the deployment in GitHub Actions tab

---

## 📋 Step-by-Step Manual Setup

### 1. Setup Secrets in Secret Manager

Run in your Cloud Shell:
```bash
# Set your project
gcloud config set project nine-tones-bots-2025-468320

# Create required secrets
echo "your_telegram_bot_token" | gcloud secrets create telegram-bot-token --data-file=-
echo "your_openai_api_key" | gcloud secrets create openai-api-key --data-file=-
gcloud secrets create google-service-account-key --data-file=path/to/your/service-account.json

# Optional configuration
echo "9_ტონა_ფული" | gcloud secrets create sheet-name --data-file=-
echo "Payments" | gcloud secrets create worksheet-name --data-file=-
```

### 2. Build and Push Docker Image

```bash
# Configure Docker for Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

# Build and push
docker build -f secure-docker-setup/Dockerfile.secure \
  -t us-central1-docker.pkg.dev/nine-tones-bots-2025-468320/tasty-ar/telegram-bot:latest .

docker push us-central1-docker.pkg.dev/nine-tones-bots-2025-468320/tasty-ar/telegram-bot:latest
```

### 3. Deploy to VM

```bash
# Upload configuration files
gcloud compute scp --recurse infra/ secure-docker-setup/ \
  tasty-tones-1:/tmp/ --zone=us-central1-c

# Configure and start services on VM
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  # Setup directories
  sudo mkdir -p /opt/telegram-bot
  sudo chown -R \$USER:\$USER /opt/telegram-bot
  cp -r /tmp/infra /tmp/secure-docker-setup /opt/telegram-bot/
  
  # Create networks and volumes
  docker network create web 2>/dev/null || true
  docker network create bot_internal --internal 2>/dev/null || true
  docker volume create caddy_data 2>/dev/null || true
  docker volume create telegram-bot_customer_data 2>/dev/null || true
  
  cd /opt/telegram-bot
  
  # Configure environment
  gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
  
  # Update compose file to use the image
  sed -i 's|build:.*|image: us-central1-docker.pkg.dev/nine-tones-bots-2025-468320/tasty-ar/telegram-bot:latest|g' secure-docker-setup/docker-compose.secure.yml
  
  # Start services
  cd infra/caddy && docker-compose up -d
  cd /opt/telegram-bot && docker-compose -f secure-docker-setup/docker-compose.secure.yml up -d
"
```

---

## 🔧 Management Commands

Once deployed, you can manage your bot with these commands:

```bash
# Check deployment status
./deploy-to-tasty-tones.sh status

# View logs
./deploy-to-tasty-tones.sh logs

# Health check
./deploy-to-tasty-tones.sh health

# Rollback if needed
./deploy-to-tasty-tones.sh rollback

# Redeploy
./deploy-to-tasty-tones.sh deploy
```

---

## 🔗 Access Points

After successful deployment:

- **Health Check**: http://35.225.153.97/health
- **Bot Health**: http://35.225.153.97/health/bot  
- **Caddy Health**: http://35.225.153.97/health/caddy

---

## 🛡️ Security Configuration

### Firewall Rules (if external access needed)
```bash
gcloud compute firewall-rules create allow-telegram-bot-http \
  --allow tcp:80,tcp:443 \
  --source-ranges 0.0.0.0/0 \
  --target-tags http-server \
  --project=nine-tones-bots-2025-468320
```

### Secret Manager Permissions
Your VM already has access to Secret Manager through the configured service account.

---

## 📊 Monitoring & Troubleshooting

### Check Container Status
```bash
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker ps"
```

### View Logs
```bash
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker logs order-bot-secure"
```

### Resource Usage
```bash
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="docker stats --no-stream"
```

### Common Issues

1. **Bot not starting**: Check secrets are properly set
2. **Health checks failing**: Verify container networking
3. **External access issues**: Check firewall rules
4. **Image pull errors**: Verify Artifact Registry authentication

---

## 🔄 Updates & Maintenance

### Update Bot Code
1. Make changes to your code
2. Run `./deploy-to-tasty-tones.sh` or push to GitHub
3. New image will be built and deployed automatically

### Update Secrets
```bash
# Update a secret
echo "new_value" | gcloud secrets versions add secret-name --data-file=-
# Then restart the bot
./deploy-to-tasty-tones.sh deploy
```

### Backup Customer Data
```bash
gcloud compute ssh tasty-tones-1 --zone=us-central1-c --command="
  docker run --rm --volumes-from order-bot-secure -v /tmp:/backup alpine \
  tar czf /backup/customers-backup-\$(date +%Y%m%d).tar.gz /app/data
"
```

---

## 🎯 Production Checklist

- ✅ Secrets stored in Secret Manager
- ✅ Non-root containers
- ✅ Health check endpoints
- ✅ Automated deployments
- ✅ Logging configured
- ✅ Resource limits set
- ✅ Network isolation
- ✅ SSL/TLS ready (when domain configured)
- ✅ Backup procedures documented

## 🆘 Support

If you encounter issues:

1. Check the deployment logs in GitHub Actions
2. Run health checks: `./deploy-to-tasty-tones.sh health`
3. Check container logs: `./deploy-to-tasty-tones.sh logs`
4. Verify secrets: `gcloud secrets list`
5. Check VM status: `gcloud compute instances describe tasty-tones-1 --zone=us-central1-c`

Your bot is now ready for production deployment with enterprise-grade security and monitoring! 🎉