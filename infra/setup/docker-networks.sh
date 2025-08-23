#!/bin/bash

# Docker Networks Setup for Telegram Bot Infrastructure
# Creates necessary networks for Caddy and bot communication

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to create network if it doesn't exist
create_network() {
    local network_name=$1
    local driver=${2:-bridge}
    local internal=${3:-false}
    
    if docker network ls --format "{{.Name}}" | grep -q "^${network_name}$"; then
        warning "Network '${network_name}' already exists"
    else
        log "Creating network: ${network_name}"
        
        if [[ "$internal" == "true" ]]; then
            docker network create \
                --driver "$driver" \
                --internal \
                "$network_name"
        else
            docker network create \
                --driver "$driver" \
                "$network_name"
        fi
        
        success "Created network: ${network_name}"
    fi
}

# Function to create volume if it doesn't exist
create_volume() {
    local volume_name=$1
    
    if docker volume ls --format "{{.Name}}" | grep -q "^${volume_name}$"; then
        warning "Volume '${volume_name}' already exists"
    else
        log "Creating volume: ${volume_name}"
        docker volume create "$volume_name"
        success "Created volume: ${volume_name}"
    fi
}

log "Setting up Docker infrastructure for Telegram Bot..."

# Create networks
log "Creating Docker networks..."

# External web network for Caddy (public-facing)
create_network "web" "bridge" "false"

# Internal network for bot communication (private)
create_network "bot_internal" "bridge" "true"

# Create persistent volumes
log "Creating Docker volumes..."

# Caddy data for SSL certificates
create_volume "caddy_data"

# Bot data for customer information
create_volume "telegram-bot_customer_data"

# Optional: Redis data if using caching
create_volume "telegram-bot_redis_data"

# Display network information
log "Network configuration:"
echo "┌─────────────────┬──────────┬──────────┬─────────────────────────────┐"
echo "│ Network Name    │ Driver   │ Internal │ Purpose                     │"
echo "├─────────────────┼──────────┼──────────┼─────────────────────────────┤"
echo "│ web             │ bridge   │ No       │ Public access via Caddy     │"
echo "│ bot_internal    │ bridge   │ Yes      │ Internal bot communication  │"
echo "└─────────────────┴──────────┴──────────┴─────────────────────────────┘"

log "Volume configuration:"
echo "┌─────────────────────────────┬─────────────────────────────────┐"
echo "│ Volume Name                 │ Purpose                         │"
echo "├─────────────────────────────┼─────────────────────────────────┤"
echo "│ caddy_data                  │ SSL certificates & Caddy data  │"
echo "│ telegram-bot_customer_data  │ Bot customer database           │"
echo "│ telegram-bot_redis_data     │ Redis cache (optional)          │"
echo "└─────────────────────────────┴─────────────────────────────────┘"

# Verify setup
log "Verifying network setup..."
if docker network inspect web &>/dev/null && docker network inspect bot_internal &>/dev/null; then
    success "✅ All networks created successfully"
else
    echo "❌ Network setup verification failed"
    exit 1
fi

log "Verifying volume setup..."
if docker volume inspect caddy_data &>/dev/null && docker volume inspect telegram-bot_customer_data &>/dev/null; then
    success "✅ All volumes created successfully"
else
    echo "❌ Volume setup verification failed"
    exit 1
fi

success "🎉 Docker infrastructure setup completed!"

# Display next steps
echo ""
log "Next steps:"
echo "1. Configure your .env file with bot credentials"
echo "2. Run: docker-compose -f infra/caddy/compose.yml up -d"
echo "3. Run: docker-compose -f secure-docker-setup/docker-compose.secure.yml up -d"
echo "4. Test health endpoints: curl http://localhost/health"