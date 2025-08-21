#!/bin/bash
# Setup SSH access to GCP VM for GitHub Actions

set -e

PROJECT_ID="${GCP_PROJECT_ID:-nine-tones-bots-2025-468320}"
VM_NAME="${VM_NAME:-telegram-bots-vm}"
ZONE="${ZONE:-europe-west3-a}"
SSH_USER="${SSH_USER:-$(whoami)}"

echo "🔑 Setting up SSH access to GCP VM"
echo "Project: $PROJECT_ID"
echo "VM: $VM_NAME"
echo "Zone: $ZONE"
echo "User: $SSH_USER"
echo "=================================="

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Please install Google Cloud SDK first."
    exit 1
fi

# Set project
gcloud config set project $PROJECT_ID

# Method 1: Generate SSH key pair for GitHub Actions
echo "🔐 Generating SSH key pair for GitHub Actions..."
ssh-keygen -t rsa -b 2048 -f ./github_vm_key -N "" -C "github-actions-$SSH_USER"

# Get the public key
PUB_KEY=$(cat github_vm_key.pub)

echo "📤 Adding SSH key to VM metadata..."

# Add SSH key to VM metadata
gcloud compute instances add-metadata $VM_NAME \
    --zone=$ZONE \
    --metadata=ssh-keys="$SSH_USER:$PUB_KEY"

# Get VM external IP
VM_IP=$(gcloud compute instances describe $VM_NAME \
    --zone=$ZONE \
    --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo "✅ SSH setup completed!"
echo ""
echo "📋 GitHub Secrets to add:"
echo "------------------------"
echo "VM_HOST: $VM_IP"
echo "VM_SSH_USER: $SSH_USER"
echo "VM_SSH_KEY: (copy content of github_vm_key file below)"
echo ""
echo "🔑 Private key content for VM_SSH_KEY secret:"
echo "=============================================="
cat github_vm_key
echo ""
echo "=============================================="
echo ""
echo "🧪 Test SSH connection:"
echo "ssh -i github_vm_key $SSH_USER@$VM_IP"
echo ""
echo "⚠️ Keep github_vm_key secure and delete after copying to GitHub secrets!"
echo "⚠️ The github_vm_key.pub can be deleted after setup."

# Test the connection
echo "🧪 Testing SSH connection..."
if ssh -i github_vm_key -o StrictHostKeyChecking=no -o ConnectTimeout=10 $SSH_USER@$VM_IP "echo 'SSH connection successful!'" 2>/dev/null; then
    echo "✅ SSH connection test passed!"
else
    echo "❌ SSH connection test failed. Check VM status and firewall rules."
    echo "   You may need to wait a few minutes for the SSH key to propagate."
fi