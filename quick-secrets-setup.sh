#!/bin/bash

# Quick Secrets Setup for Your Existing GCP Environment
# Run this in your Cloud Shell to setup Secret Manager secrets

set -euo pipefail

# Your configuration
PROJECT_ID="nine-tones-bots-2025-468320"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

header() {
    echo ""
    echo -e "${GREEN}=== $1 ===${NC}"
}

# Set project
gcloud config set project "$PROJECT_ID"

header "Quick Secret Manager Setup for Telegram Bot"

echo "This script will help you set up the required secrets in Google Secret Manager."
echo "Project: $PROJECT_ID"
echo ""

# Function to create secret
create_secret() {
    local secret_name=$1
    local description=$2
    local prompt=$3
    local is_file=${4:-false}
    
    log "Setting up: $secret_name"
    
    # Check if secret exists
    if gcloud secrets describe "$secret_name" --project="$PROJECT_ID" &>/dev/null; then
        warning "Secret '$secret_name' already exists"
        read -p "Update it? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 0
        fi
    else
        log "Creating new secret: $secret_name"
        gcloud secrets create "$secret_name" \
            --replication-policy="automatic" \
            --project="$PROJECT_ID"
    fi
    
    # Add secret value
    echo ""
    echo "$prompt"
    
    if [[ "$is_file" == "true" ]]; then
        while true; do
            read -p "Enter file path: " file_path
            if [[ -f "$file_path" ]]; then
                gcloud secrets versions add "$secret_name" \
                    --data-file="$file_path" \
                    --project="$PROJECT_ID"
                success "✅ Secret '$secret_name' updated from file"
                break
            else
                error "File not found: $file_path. Please try again."
            fi
        done
    else
        while true; do
            read -s -p "Enter value: " secret_value
            echo
            if [[ -n "$secret_value" ]]; then
                echo "$secret_value" | gcloud secrets versions add "$secret_name" \
                    --data-file=- \
                    --project="$PROJECT_ID"
                success "✅ Secret '$secret_name' updated"
                break
            else
                error "Empty value provided. Please enter a valid value."
            fi
        done
    fi
    echo ""
}

header "Required Secrets Setup"

# 1. Telegram Bot Token
create_secret "telegram-bot-token" \
    "Telegram Bot Token" \
    "📱 Please enter your Telegram Bot Token (get from @BotFather):"

# 2. OpenAI API Key  
create_secret "openai-api-key" \
    "OpenAI API Key" \
    "🤖 Please enter your OpenAI API Key (get from https://platform.openai.com/api-keys):"

# 3. Google Service Account
echo "📋 For Google Sheets integration, you need a service account JSON file."
echo "If you don't have one:"
echo "1. Go to https://console.cloud.google.com/iam-admin/serviceaccounts"
echo "2. Create a service account"
echo "3. Download the JSON key file"
echo "4. Enable Google Sheets API"
echo ""

read -p "Do you have a Google service account JSON file? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    create_secret "google-service-account-key" \
        "Google Service Account JSON" \
        "📊 Please provide the path to your Google service account JSON file:" \
        true
else
    warning "⚠️ Skipping Google service account setup. You can add this later."
fi

header "Optional Configuration"

# Optional: Sheet name
echo "📄 Default Google Sheet name is '9_ტონა_ფული'"
read -p "Do you want to use a different sheet name? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    create_secret "sheet-name" \
        "Google Sheet Name" \
        "📄 Enter your Google Sheet name:"
fi

# Optional: Worksheet name
echo "📋 Default worksheet name is 'Payments'"
read -p "Do you want to use a different worksheet name? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    create_secret "worksheet-name" \
        "Worksheet Name" \
        "📋 Enter your worksheet name:"
fi

header "Setup Complete!"

echo "✅ Secret Manager setup completed!"
echo ""
echo "📋 Secrets created in project: $PROJECT_ID"
gcloud secrets list --project="$PROJECT_ID" --filter="name:telegram-bot OR name:openai OR name:google-service OR name:sheet"
echo ""

echo "🚀 Next steps:"
echo "1. Run the deployment script: ./deploy-to-tasty-tones.sh"
echo "2. Or push to GitHub to trigger automated deployment"
echo ""

echo "🔗 Quick access commands:"
echo "   Deploy: ./deploy-to-tasty-tones.sh"
echo "   Health check: ./deploy-to-tasty-tones.sh health"
echo "   View logs: ./deploy-to-tasty-tones.sh logs"
echo "   Check status: ./deploy-to-tasty-tones.sh status"

echo ""
success "🎉 Ready for deployment!"