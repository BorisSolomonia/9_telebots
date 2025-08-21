#!/bin/bash
# Setup SSH key for VM deployment

PROJECT_ID="nine-tones-bots-2025-468320"
VM_NAME="vm-runtime"
ZONE="europe-west3-b"

echo "🔑 Setting up SSH key for VM deployment"
echo "======================================"
echo "Project: $PROJECT_ID"
echo "VM: $VM_NAME"
echo "Zone: $ZONE"
echo ""

# Generate SSH key pair
echo "1️⃣ Generating SSH key pair..."
ssh-keygen -t rsa -b 2048 -f ./github_vm_ssh_key -N "" -C "github-actions-deploy"

echo ""
echo "2️⃣ Adding SSH key to VM..."

# Get current user
VM_USER=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" | cut -d'@' -f1)
echo "VM User: $VM_USER"

# Add SSH key to VM metadata
PUB_KEY=$(cat github_vm_ssh_key.pub)
gcloud compute instances add-metadata $VM_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --metadata=ssh-keys="$VM_USER:$PUB_KEY"

echo ""
echo "3️⃣ Testing SSH connection..."
VM_IP=$(gcloud compute instances describe $VM_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo "VM IP: $VM_IP"

# Test SSH connection
if ssh -i github_vm_ssh_key -o StrictHostKeyChecking=no -o ConnectTimeout=10 $VM_USER@$VM_IP "echo 'SSH connection successful!'" 2>/dev/null; then
    echo "✅ SSH connection test passed!"
else
    echo "⚠️ SSH connection test failed. This is normal - the key may need a few minutes to propagate."
fi

echo ""
echo "4️⃣ GitHub Secrets to add:"
echo "========================="
echo ""
echo "VM_SSH_USER:"
echo "$VM_USER"
echo ""
echo "VM_SSH_KEY (copy the private key below):"
echo "----------------------------------------"
cat github_vm_ssh_key
echo "----------------------------------------"
echo ""
echo "✅ Setup completed!"
echo ""
echo "📋 Next steps:"
echo "1. Copy the VM_SSH_USER and VM_SSH_KEY values above"
echo "2. Add them as GitHub repository secrets"
echo "3. Replace your current deploy.yml with deploy-ssh.yml"
echo "4. Push to trigger SSH-based deployment"
echo ""
echo "🔒 Security: Delete the key files after adding to GitHub:"
echo "rm github_vm_ssh_key github_vm_ssh_key.pub"