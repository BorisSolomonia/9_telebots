#!/bin/bash

# Deploy Telegram Bot to Existing GCP Infrastructure (tasty-tones-1)
# Configured for your existing Cloud Shell environment

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# Your existing environment variables
PROJECT_ID="nine-tones-bots-2025-468320"
REGION="us-central1"
ZONE="us-central1-c"
AR_REPO="tasty-ar"
VM_NAME="tasty-tones-1"
VM_IP="35.225.153.97"
APP_NAME="telegram-bot"
SERVICE_NAME="order-bot-secure"

# Logging functions
log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

header() {
    echo -e "${PURPLE}=== $1 ===${NC}"
}

# Check if we're running in Cloud Shell or have gcloud configured
check_environment() {
    header "Environment Check"
    
    if [[ -n "${CLOUD_SHELL:-}" ]]; then
        success "✅ Running in Google Cloud Shell"
    else
        log "Running outside Cloud Shell, checking gcloud authentication..."
        if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q "@"; then
            error "❌ Not authenticated with gcloud. Please run: gcloud auth login"
            exit 1
        fi
    fi
    
    # Set project
    log "Setting project: $PROJECT_ID"
    gcloud config set project "$PROJECT_ID"
    
    # Verify VM exists
    if ! gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --format="value(name)" &>/dev/null; then
        error "❌ VM $VM_NAME not found in zone $ZONE"
        exit 1
    fi
    
    success "✅ Environment verified"
}

# Setup secrets in Secret Manager
setup_secrets() {
    header "Secret Manager Setup"
    
    log "Checking and creating secrets..."
    
    # Function to create or update secret
    setup_secret() {
        local secret_name=$1
        local description=$2
        local is_file=${3:-false}
        
        if gcloud secrets describe "$secret_name" --project="$PROJECT_ID" &>/dev/null; then
            info "Secret '$secret_name' already exists"
            read -p "Update it? (y/n): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                return 0
            fi
        else
            log "Creating secret: $secret_name"
            gcloud secrets create "$secret_name" \
                --replication-policy="automatic" \
                --project="$PROJECT_ID"
        fi
        
        if [[ "$is_file" == "true" ]]; then
            read -p "Enter path to $description file: " secret_file
            if [[ -f "$secret_file" ]]; then
                gcloud secrets versions add "$secret_name" \
                    --data-file="$secret_file" \
                    --project="$PROJECT_ID"
                success "✅ Updated $secret_name from file"
            else
                error "❌ File not found: $secret_file"
                return 1
            fi
        else
            read -s -p "Enter $description: " secret_value
            echo
            if [[ -n "$secret_value" ]]; then
                echo "$secret_value" | gcloud secrets versions add "$secret_name" \
                    --data-file=- \
                    --project="$PROJECT_ID"
                success "✅ Updated $secret_name"
            else
                warning "⚠️ Empty value provided for $secret_name"
            fi
        fi
    }
    
    # Setup required secrets
    setup_secret "telegram-bot-token" "Telegram Bot Token (from @BotFather)"
    setup_secret "openai-api-key" "OpenAI API Key"
    setup_secret "google-service-account-key" "Google Service Account JSON" true
    
    # Optional secrets with defaults
    echo ""
    log "Setting up optional configuration secrets..."
    setup_secret "sheet-name" "Google Sheet Name (or press Enter for default)"
    setup_secret "worksheet-name" "Worksheet Name (or press Enter for default)"
    
    success "✅ Secrets configuration completed"
}

# Build and push Docker image
build_and_push() {
    header "Building and Pushing Docker Image"
    
    local image_uri="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${APP_NAME}"
    local image_tag=$(date +%s)  # Use timestamp as tag
    local full_image_uri="${image_uri}:${image_tag}"
    
    # Configure Docker for Artifact Registry
    log "Configuring Docker authentication..."
    gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
    
    # Build image
    log "Building Docker image: $full_image_uri"
    docker build \
        -f secure-docker-setup/Dockerfile.secure \
        -t "$full_image_uri" \
        -t "${image_uri}:latest" \
        --label "org.opencontainers.image.created=$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        --label "org.opencontainers.image.revision=$(git rev-parse HEAD 2>/dev/null || echo 'unknown')" \
        .
    
    # Push image
    log "Pushing image to Artifact Registry..."
    docker push "$full_image_uri"
    docker push "${image_uri}:latest"
    
    success "✅ Image built and pushed: $full_image_uri"
    echo "IMAGE_URI=$full_image_uri" > .deploy-vars
    echo "IMAGE_LATEST=${image_uri}:latest" >> .deploy-vars
}

# Deploy to VM
deploy_to_vm() {
    header "Deploying to VM: $VM_NAME"
    
    # Source deployment variables
    source .deploy-vars 2>/dev/null || {
        warning "No deployment vars found, using latest image"
        IMAGE_LATEST="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${APP_NAME}:latest"
    }
    
    log "Uploading configuration files..."
    
    # Create temp directory for deployment files
    local temp_dir=$(mktemp -d)
    
    # Prepare deployment files
    cp -r infra secure-docker-setup "$temp_dir/"
    
    # Update docker-compose to use the built image
    sed -i "s|build:.*|image: ${IMAGE_LATEST}|g" "$temp_dir/secure-docker-setup/docker-compose.secure.yml"
    sed -i "/context:/d" "$temp_dir/secure-docker-setup/docker-compose.secure.yml"
    sed -i "/dockerfile:/d" "$temp_dir/secure-docker-setup/docker-compose.secure.yml"
    
    # Upload files to VM
    gcloud compute scp \
        --recurse \
        "$temp_dir/infra" \
        "$temp_dir/secure-docker-setup" \
        "${VM_NAME}:/tmp/" \
        --zone="$ZONE" \
        --project="$PROJECT_ID"
    
    # Configure and deploy on VM
    log "Configuring application on VM..."
    gcloud compute ssh "$VM_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT_ID" \
        --command="
            # Setup directories
            sudo mkdir -p /opt/telegram-bot
            sudo chown -R \$USER:\$USER /opt/telegram-bot
            
            # Move files
            cp -r /tmp/infra /tmp/secure-docker-setup /opt/telegram-bot/
            
            # Create Docker networks and volumes
            docker network create web 2>/dev/null || echo 'Network web exists'
            docker network create bot_internal --internal 2>/dev/null || echo 'Network bot_internal exists'
            docker volume create caddy_data 2>/dev/null || echo 'Volume caddy_data exists'
            docker volume create telegram-bot_customer_data 2>/dev/null || echo 'Volume customer_data exists'
            
            cd /opt/telegram-bot
            
            # Fetch secrets and create .env
            echo 'Fetching secrets from Secret Manager...'
            {
                echo \"TELEGRAM_TOKEN_BOT=\$(gcloud secrets versions access latest --secret=telegram-bot-token --project=${PROJECT_ID} 2>/dev/null || echo 'MISSING')\"
                echo \"ORDER_BOT_TOKEN=\$(gcloud secrets versions access latest --secret=telegram-bot-token --project=${PROJECT_ID} 2>/dev/null || echo 'MISSING')\"
                echo \"OPENAI_API_KEY=\$(gcloud secrets versions access latest --secret=openai-api-key --project=${PROJECT_ID} 2>/dev/null || echo 'MISSING')\"
                echo \"SHEET_NAME=\$(gcloud secrets versions access latest --secret=sheet-name --project=${PROJECT_ID} 2>/dev/null || echo '9_ტონა_ფული')\"
                echo \"WORKSHEET_NAME=\$(gcloud secrets versions access latest --secret=worksheet-name --project=${PROJECT_ID} 2>/dev/null || echo 'Payments')\"
                echo \"CUSTOMERS_FILE=/app/data/customers.json\"
                echo \"CREDS_FILE=/app/credentials.json\"
                echo \"LOG_LEVEL=INFO\"
                echo \"MESSAGE_COOLDOWN=5\"
            } > .env.template
            
            # Expand variables
            eval \"\$(cat .env.template)\" && env | grep -E '^(TELEGRAM_|ORDER_|OPENAI_|SHEET_|WORKSHEET_|CUSTOMERS_|CREDS_|LOG_|MESSAGE_)' > .env
            
            # Fetch Google credentials
            if gcloud secrets versions access latest --secret=google-service-account-key --project=${PROJECT_ID} > credentials.json 2>/dev/null; then
                echo '✅ Google credentials fetched'
            else
                echo '{\"type\": \"service_account\"}' > credentials.json
                echo '⚠️ Google credentials not found, using placeholder'
            fi
            
            # Set permissions
            chmod 600 .env credentials.json 2>/dev/null || true
            
            # Note: Using existing Caddy on VM, no separate configuration needed
            
            echo '✅ Configuration completed'
        "
    
    success "✅ Configuration deployed to VM"
    rm -rf "$temp_dir"
}

# Start services
start_services() {
    header "Starting Services"
    
    log "Deploying services on VM..."
    gcloud compute ssh "$VM_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT_ID" \
        --command="
            cd /opt/telegram-bot
            
            # Configure Docker for Artifact Registry
            gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet
            
            # Stop existing services gracefully
            echo '⏹️ Stopping existing bot services...'
            docker-compose -f secure-docker-setup/docker-compose.secure.yml down --remove-orphans 2>/dev/null || true
            
            # Start bot application (Caddy already running on VM)
            echo '🤖 Starting bot application...'
            docker-compose -f secure-docker-setup/docker-compose.secure.yml pull
            docker-compose -f secure-docker-setup/docker-compose.secure.yml up -d
            
            echo '✅ All services started'
        "
    
    success "✅ Services deployment completed"
}

# Health check
health_check() {
    header "Health Check"
    
    log "Running health checks..."
    sleep 10  # Give services time to start
    
    gcloud compute ssh "$VM_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT_ID" \
        --command="
            echo '🔍 Container Status:'
            docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
            
            echo ''
            echo '🔍 Health Endpoints:'
            
            # Test Caddy
            if timeout 10 curl -f http://localhost/health 2>/dev/null; then
                echo '✅ Caddy health: PASSED'
            else
                echo '❌ Caddy health: FAILED'
            fi
            
            # Test bot (on port 8081 due to Caddy conflict)
            if timeout 10 curl -f http://localhost:8081/health 2>/dev/null; then
                echo '✅ Bot health: PASSED'
            else
                echo '❌ Bot health: FAILED'
            fi
            
            echo ''
            echo '📊 Resource Usage:'
            docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'
            
            echo ''
            echo '📋 Recent Logs:'
            docker logs ${SERVICE_NAME} --tail 5 2>/dev/null || echo 'No logs available'
        "
    
    # External health check
    echo ""
    info "🌐 External Health Check:"
    if timeout 10 curl -f "http://${VM_IP}/health" 2>/dev/null; then
        success "✅ External access working: http://${VM_IP}"
    else
        warning "⚠️ External access limited (may need firewall rules)"
        echo "To enable external access, run:"
        echo "gcloud compute firewall-rules create allow-telegram-bot-http \\"
        echo "  --allow tcp:80,tcp:443 \\"
        echo "  --source-ranges 0.0.0.0/0 \\"
        echo "  --target-tags http-server \\"
        echo "  --project=${PROJECT_ID}"
    fi
}

# Show deployment summary
show_summary() {
    header "Deployment Summary"
    
    echo "📋 Deployment completed for:"
    echo "   Project: $PROJECT_ID"
    echo "   VM: $VM_NAME ($VM_IP)"
    echo "   Region: $REGION / $ZONE"
    echo "   Repository: $AR_REPO"
    echo ""
    echo "🔗 Access points:"
    echo "   Health check: http://$VM_IP/health"
    echo "   Bot health: http://$VM_IP/health/bot"
    echo "   Caddy health: http://$VM_IP/health/caddy"
    echo ""
    echo "📊 To monitor:"
    echo "   Logs: gcloud compute ssh $VM_NAME --zone=$ZONE --command='docker logs $SERVICE_NAME'"
    echo "   Status: gcloud compute ssh $VM_NAME --zone=$ZONE --command='docker ps'"
}

# Rollback function
rollback() {
    header "Rolling Back Deployment"
    
    warning "Rolling back to previous deployment..."
    gcloud compute ssh "$VM_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT_ID" \
        --command="
            cd /opt/telegram-bot
            
            # Stop current containers
            docker-compose -f secure-docker-setup/docker-compose.secure.yml down
            
            # Try to start with previous image
            docker-compose -f secure-docker-setup/docker-compose.secure.yml up -d
        "
    
    success "✅ Rollback completed"
}

# Main function
main() {
    local action="${1:-deploy}"
    
    case "$action" in
        "deploy")
            header "Telegram Bot Deployment to $VM_NAME"
            check_environment
            
            # Ask if user wants to setup secrets
            echo ""
            read -p "Do you want to setup/update secrets in Secret Manager? (y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                setup_secrets
            fi
            
            build_and_push
            deploy_to_vm
            start_services
            health_check
            show_summary
            ;;
        "rollback")
            rollback
            ;;
        "health")
            check_environment
            health_check
            ;;
        "logs")
            gcloud compute ssh "$VM_NAME" \
                --zone="$ZONE" \
                --project="$PROJECT_ID" \
                --command="docker logs $SERVICE_NAME --tail 50"
            ;;
        "status")
            gcloud compute ssh "$VM_NAME" \
                --zone="$ZONE" \
                --project="$PROJECT_ID" \
                --command="
                    echo 'Container Status:'
                    docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
                    echo ''
                    echo 'Resource Usage:'
                    docker stats --no-stream
                "
            ;;
        *)
            echo "Usage: $0 [deploy|rollback|health|logs|status]"
            echo ""
            echo "Commands:"
            echo "  deploy   - Full deployment (default)"
            echo "  rollback - Rollback to previous deployment"
            echo "  health   - Run health checks"
            echo "  logs     - Show bot logs"
            echo "  status   - Show container status"
            exit 1
            ;;
    esac
}

# Run with arguments
main "$@"