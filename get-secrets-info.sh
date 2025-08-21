#!/bin/bash
# Get information needed for GitHub Secrets

PROJECT_ID="nine-tones-bots-2025-468320"  # From your error logs

echo "🔑 GitHub Secrets Configuration"
echo "==============================="
echo ""
echo "1. GCP_PROJECT_ID:"
echo "   Value: $PROJECT_ID"
echo ""

echo "2. GCP_SA_KEY:"
echo "   Run: ./secrets-setup.sh"
echo "   Then copy content of: github-deploy-key.json"
echo ""

echo "3. VM_HOST (your VM external IP):"
echo "   Run: gcloud compute instances describe telegram-bots-vm --zone=europe-west3-a --format='get(networkInterfaces[0].accessConfigs[0].natIP)'"
echo ""

echo "4. VM_SSH_USER (your username):"
echo "   Usually your Google account username before @gmail.com"
echo "   Or run: whoami"
echo ""

echo "5. VM_SSH_KEY (generate SSH key for VM):"
echo "   Run: ssh-keygen -t rsa -b 2048 -f ~/.ssh/gcp_vm_key -C 'your-username'"
echo "   Then add public key to VM metadata"
echo "   Copy PRIVATE key content for GitHub secret"
echo ""

echo "🔧 Alternative: Use existing service account for VM access"
echo "   Add VM access to your service account instead of SSH keys"