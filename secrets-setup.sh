#!/bin/bash
# GCP Secret Manager Setup Script for Telegram Bots
# Run this script to create all required secrets

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-nine-tones-bots-2025}"
REGION="europe-west3"

echo "🔐 Setting up GCP Secret Manager for Telegram Bots"
echo "Project ID: $PROJECT_ID"
echo "=================================="

# Check if gcloud is installed and authenticated
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Please install Google Cloud SDK first."
    exit 1
fi

# Set project
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "📡 Enabling required APIs..."
gcloud services enable secretmanager.googleapis.com
gcloud services enable compute.googleapis.com
gcloud services enable artifactregistry.googleapis.com

# Create secrets for telegram bots
echo "🤖 Creating Telegram Bot secrets..."

# Create environment file secret
if [ -f ".env.production" ]; then
    echo "Creating telegram-bots-env secret..."
    gcloud secrets create telegram-bots-env \
        --data-file=.env.production \
        --replication-policy="automatic" || echo "Secret already exists"
else
    echo "❌ .env.production file not found"
    exit 1
fi

# Create individual secrets for sensitive data
echo "Creating individual bot token secrets..."

# Payment Bot Token
read -p "Enter Payment Bot Token (TELEGRAM_TOKEN_BOT): " PAYMENT_TOKEN
echo -n "$PAYMENT_TOKEN" | gcloud secrets create telegram-payment-bot-token \
    --data-file=- \
    --replication-policy="automatic" || echo "Secret already exists"

# Order Bot Token  
read -p "Enter Order Bot Token (ORDER_BOT_TOKEN): " ORDER_TOKEN
echo -n "$ORDER_TOKEN" | gcloud secrets create telegram-order-bot-token \
    --data-file=- \
    --replication-policy="automatic" || echo "Secret already exists"

# OpenAI API Key
read -p "Enter OpenAI API Key: " OPENAI_KEY
echo -n "$OPENAI_KEY" | gcloud secrets create openai-api-key \
    --data-file=- \
    --replication-policy="automatic" || echo "Secret already exists"

# Google Sheets Credentials
if [ -f "credentials.json" ]; then
    echo "Creating sheets-credentials secret..."
    gcloud secrets create sheets-credentials \
        --data-file=credentials.json \
        --replication-policy="automatic" || echo "Secret already exists"
else
    echo "⚠️ credentials.json not found - you'll need to upload this manually"
fi

# Customer Data
if [ -f "customers.json" ]; then
    echo "Creating customers-data secret..."
    gcloud secrets create customers-data \
        --data-file=customers.json \
        --replication-policy="automatic" || echo "Secret already exists"
else
    echo "⚠️ customers.json not found - you'll need to upload this manually"
fi

# Create service account for GitHub Actions if it doesn't exist
echo "🔧 Setting up GitHub Actions service account..."
SA_EMAIL="github-deploy@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create github-deploy \
    --display-name="GitHub Deploy Service Account" \
    --description="Service account for GitHub Actions deployments" || echo "Service account already exists"

# Grant necessary permissions
echo "🔑 Granting permissions..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/compute.instanceAdmin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/compute.osLogin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/iam.serviceAccountUser"

# Create and download service account key
echo "📥 Creating service account key..."
gcloud iam service-accounts keys create github-deploy-key.json \
    --iam-account="${SA_EMAIL}"

echo "✅ GCP Secret Manager setup completed!"
echo ""
echo "📋 Next steps:"
echo "1. Upload github-deploy-key.json content to GitHub Secrets as GCP_SA_KEY"
echo "2. Set the following GitHub repository secrets:"
echo "   - GCP_PROJECT_ID: $PROJECT_ID"
echo "   - VM_HOST: your-vm-ip-address"
echo "   - VM_SSH_USER: your-vm-username"
echo "   - VM_SSH_KEY: your-vm-ssh-private-key"
echo ""
echo "3. Update secrets as needed:"
echo "   gcloud secrets versions add telegram-bots-env --data-file=new-env-file"
echo ""
echo "🗑️  Remember to delete github-deploy-key.json after uploading to GitHub!"