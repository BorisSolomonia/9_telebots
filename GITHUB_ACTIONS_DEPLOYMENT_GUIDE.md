# GitHub Actions Deployment Guide: Telegram Bot to GCP

## Overview

This guide documents all issues encountered during GitHub Actions deployment setup for a containerized Telegram bot to Google Cloud Platform, their root causes, and proven solutions. Use this as a reference to avoid common pitfalls and build robust CI/CD pipelines.

## Critical Issues & Solutions

### 1. 🚨 Job Outputs Being Filtered as Secrets

**Issue**: GitHub Actions automatically filters job outputs containing sensitive-looking values
```yaml
# This FAILS - GitHub skips outputs with project IDs, registry URLs
outputs:
  image_uri: ${{ steps.build.outputs.image_uri }}  # Contains project ID
```

**Error Message**: 
```
Warning: Skip output 'image_uri' since it may contain secret.
```

**❌ Root Cause**: GitHub's security feature prevents passing outputs that look like secrets between jobs.

**✅ Solution**: Construct values directly in deployment step using individual secrets
```yaml
# In deployment step - bypass job outputs entirely
env:
  AR_REGION: ${{ secrets.AR_REGION }}
  GCP_PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
  AR_REPO_NAME: ${{ secrets.AR_REPO_NAME }}
  APP_NAME: ${{ secrets.APP_NAME }}
  GITHUB_SHA: ${{ github.sha }}

script: |
  # Construct IMAGE_URI directly
  AR_HOST="${AR_REGION}-docker.pkg.dev"
  IMAGE_URI="${AR_HOST}/${GCP_PROJECT_ID}/${AR_REPO_NAME}/${APP_NAME}:${GITHUB_SHA}"
```

### 2. 🚨 Environment Variables Not Reaching Remote VM

**Issue**: Variables set in `env:` section don't appear in remote SSH session

**❌ Wrong Approach**: 
```yaml
env:
  MY_VAR: ${{ secrets.MY_SECRET }}
script: |
  echo $MY_VAR  # This is empty!
```

**✅ Correct Approach**: Use `envs:` parameter to forward variables
```yaml
env:
  MY_VAR: ${{ secrets.MY_SECRET }}
  ANOTHER_VAR: ${{ env.ANOTHER_VAR }}
with:
  envs: MY_VAR,ANOTHER_VAR  # Explicitly forward these
script: |
  echo $MY_VAR  # Now this works!
```

### 3. 🚨 SCP Action Directory Permission Issues

**Issue**: SCP fails to create target directories in `/opt/`

**Error**: 
```
create folder /opt/app-name/
drone-scp error: Process exited with status 1
```

**✅ Solution**: Pre-create directory with proper permissions
```yaml
- name: 📁 Ensure target directory exists
  uses: appleboy/ssh-action@v1.0.3
  env:
    APP_NAME: ${{ secrets.APP_NAME }}
  with:
    envs: APP_NAME
    script: |
      APP_DIR="/opt/$APP_NAME"
      sudo mkdir -p "$APP_DIR"
      sudo chown "$USER:$USER" "$APP_DIR"
```

### 4. 🚨 Empty Compose File Errors

**Issue**: Docker Compose reports "empty compose file" during operations

**Multiple Root Causes**:
- Network mismatch between compose file and script
- Commented-out compose files being processed
- Operations running before file setup is complete

**✅ Solutions**:

**A) Network Alignment**:
```yaml
# Create networks matching your compose file
docker network create bot_network --internal 2>/dev/null || true
# Not: docker network create bot_internal
```

**B) Skip Empty Compose Files**:
```yaml
# Check if compose file has active services before using
if grep -q "^[[:space:]]*[^#].*:" compose.yml 2>/dev/null; then
  docker-compose up -d
else
  echo "Compose file empty - skipping"
fi
```

**C) Operation Ordering**:
```yaml
# 1. Fix files FIRST
# 2. Create networks
# 3. Run docker compose operations
```

### 5. 🚨 YAML Corruption from sed Operations

**Issue**: sed replacements break YAML structure

**❌ Problem**: 
```yaml
# Original:
build:
  context: ..
  dockerfile: Dockerfile

# After naive sed replacement:
image: my-image:tag
  context: ..        # Orphaned lines break YAML
  dockerfile: Dockerfile
```

**✅ Solution**: Handle multi-line blocks properly
```bash
# Replace build: line and remove orphaned lines
sed -i "s|^\s*build:\s*$|    image: ${IMAGE_URI}|g" compose.yml
sed -i "/^\s*context:/d" compose.yml
sed -i "/^\s*dockerfile:/d" compose.yml
```

### 6. 🚨 File Location Mismatches

**Issue**: Files copied to wrong locations relative to compose file expectations

**Example**: `.env` copied to `/opt/app/` but compose file expects `/opt/app/secure-docker-setup/.env`

**✅ Solution**: Verify and fix file locations
```bash
# Check where files are and where they're needed
if [ -f ".env" ] && [ ! -f "secure-docker-setup/.env" ]; then
  cp .env secure-docker-setup/.env
fi
```

## Best Practices for Deployment YAML

### 1. Structure Your Workflow Jobs

```yaml
jobs:
  build-and-push:
    # ✅ Build and push image - simple job with minimal outputs
    outputs: {} # Don't rely on job outputs for sensitive data
  
  deploy:
    needs: build-and-push
    # ✅ Construct all values from secrets in deployment step
```

### 2. Secret Management Strategy

**Create these GitHub Secrets**:
```bash
# Core Application
APP_NAME=your-app-name
GCP_PROJECT_ID=your-project-id

# Artifact Registry  
AR_REGION=us-central1
AR_REPO_NAME=your-ar-repo

# Infrastructure
VM_HOST=your-vm-ip
VM_SSH_USER=your-ssh-user
VM_SSH_KEY=your-private-key

# Service Account
GCP_SA_KEY=your-service-account-json
```

**Use GCP Secret Manager for runtime secrets**:
```bash
# Create secret containing all environment variables
gcloud secrets create app1-env --data-file=.env
```

### 3. Robust SSH Action Pattern

```yaml
- name: Deploy Application
  uses: appleboy/ssh-action@v1.0.3
  env:
    # ✅ Pass individual secrets, not composite values
    APP_NAME: ${{ secrets.APP_NAME }}
    AR_REGION: ${{ secrets.AR_REGION }}
    GCP_PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
    GITHUB_SHA: ${{ github.sha }}
  with:
    host: ${{ secrets.VM_HOST }}
    username: ${{ secrets.VM_SSH_USER }}
    key: ${{ secrets.VM_SSH_KEY }}
    envs: APP_NAME,AR_REGION,GCP_PROJECT_ID,GITHUB_SHA
    script: |
      set -euo pipefail  # ✅ Fail fast on errors
      
      # ✅ Construct sensitive values in remote context
      IMAGE_URI="${AR_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/repo/${APP_NAME}:${GITHUB_SHA}"
      
      # ✅ Validate all required values
      if [[ -z "$IMAGE_URI" ]]; then
        echo "❌ Failed to construct IMAGE_URI"
        exit 1
      fi
      
      # ✅ Continue with deployment...
```

### 4. File and Network Setup Pattern

```yaml
script: |
  # ✅ 1. Setup files FIRST
  if [ -f ".env" ] && [ ! -f "target/.env" ]; then
    cp .env target/.env
  fi
  
  # ✅ 2. Fix compose files
  sed -i "s|build:.*|image: ${IMAGE_URI}|g" compose.yml
  
  # ✅ 3. Validate YAML
  if ! docker-compose -f compose.yml config --quiet; then
    echo "❌ Invalid YAML"
    exit 1
  fi
  
  # ✅ 4. Create networks
  docker network create app_network 2>/dev/null || true
  
  # ✅ 5. Deploy
  docker-compose up -d
```

### 5. Error Handling & Debugging

```yaml
script: |
  # ✅ Add debugging for complex operations
  echo "🔍 Current directory: $(pwd)"
  echo "🔍 Available files:"
  ls -la
  
  # ✅ Validate assumptions
  if [ ! -f "compose.yml" ]; then
    echo "❌ Compose file missing"
    exit 1
  fi
  
  # ✅ Show progress clearly  
  echo "✅ Files verified"
  echo "✅ Networks created"
  echo "✅ Deployment starting"
```

## Project-Specific Considerations

### For This Telegram Bot Project:

1. **Multiple Bot Variants**: Use `APP_NAME` to distinguish between `app1`, `app2`, etc.

2. **Redis Dependency**: Always add `REDIS_PASSWORD` to `.env` files:
```bash
if ! grep -q "REDIS_PASSWORD" .env; then
  echo "REDIS_PASSWORD=secure_pass_$(openssl rand -hex 12)" >> .env
fi
```

3. **Network Configuration**: Match compose file networks:
```yaml
# Compose file uses bot_network, not bot_internal
docker network create bot_network --internal 2>/dev/null || true
```

4. **Optional Components**: Handle Caddy gracefully:
```bash
# Skip if compose file is commented out
if grep -q "^[[:space:]]*[^#].*:" caddy/compose.yml; then
  docker-compose up -d
else
  echo "Caddy disabled - skipping"
fi
```

5. **Health Checks**: Use actual container names:
```bash
# Use specific container name, not variable
docker logs order-bot-secure --tail 200
```

## Anti-Patterns to Avoid

### ❌ DON'T: Rely on Job Outputs for Sensitive Data
```yaml
# This gets filtered by GitHub
outputs:
  image_uri: us-central1-docker.pkg.dev/project/repo/app:tag
```

### ❌ DON'T: Assume Networks Exist
```bash
# This fails if network doesn't exist
docker-compose up -d
```

### ❌ DON'T: Use Naive sed Replacements
```bash
# This breaks YAML structure
sed -i "s/build:.*/image: $IMAGE/" compose.yml
```

### ❌ DON'T: Skip Error Handling
```bash
# Silent failures are hard to debug
docker-compose up -d || true  # Don't do this
```

## Testing Your Deployment

### 1. Test Locally First
```bash
# Simulate the deployment script locally
export AR_REGION=us-central1
export GCP_PROJECT_ID=your-project
# Run your script sections
```

### 2. Use Workflow Dispatch
```yaml
on:
  workflow_dispatch: {}  # Manual trigger for testing
```

### 3. Add Validation Steps
```yaml
- name: Validate Deployment
  run: |
    # Check containers are running
    if ! docker ps | grep -q "your-app"; then
      echo "❌ App container not running"
      exit 1
    fi
```

## Quick Recovery Commands

If deployment fails, use these commands on your VM:

```bash
# Check container status
docker ps -a

# View logs
docker logs order-bot-secure --tail 50

# Restart deployment
cd /opt/app1
docker-compose -f secure-docker-setup/docker-compose.secure.yml up -d

# Clean restart
docker-compose down
docker system prune -f
docker-compose up -d
```

## Summary

The key to successful GitHub Actions deployment is:

1. **Never rely on job outputs for sensitive data** - construct values in deployment step
2. **Always use `envs:` parameter** for SSH actions
3. **Setup files and networks before using them**
4. **Handle optional components gracefully**
5. **Add comprehensive validation and debugging**
6. **Test the complete flow before production**

Following these patterns will save hours of debugging and create more reliable deployments.