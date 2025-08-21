#!/bin/bash
# Debug SSH connection issues

echo "🔍 SSH CONNECTION DEBUGGING"
echo "=========================="

# Check if key files exist
if [ -f "github_vm_ssh_key" ]; then
    echo "✅ Private key file exists"
    
    echo ""
    echo "📋 Private key format (first/last lines):"
    head -1 github_vm_ssh_key
    echo "..."
    tail -1 github_vm_ssh_key
    echo ""
    
    echo "📊 Key file stats:"
    wc -l github_vm_ssh_key
    
    echo ""
    echo "🔑 Key fingerprint:"
    ssh-keygen -lf github_vm_ssh_key
    
else
    echo "❌ Private key file missing - regenerating..."
    ssh-keygen -t rsa -b 2048 -f ./github_vm_ssh_key -N "" -C "github-actions-deploy"
fi

if [ -f "github_vm_ssh_key.pub" ]; then
    echo "✅ Public key file exists"
    echo ""
    echo "📋 Public key content:"
    cat github_vm_ssh_key.pub
else
    echo "❌ Public key file missing"
fi

echo ""
echo "🧪 Testing SSH connection..."
echo "VM IP: 34.141.45.73"
echo "User: borissolomonia"

# Test with verbose output
ssh -i github_vm_ssh_key -o StrictHostKeyChecking=no -o ConnectTimeout=10 -v borissolomonia@34.141.45.73 "echo 'SSH test successful'" 2>&1 | head -20

echo ""
echo "📋 GitHub Secret Format:"
echo "========================"
echo "VM_SSH_USER: borissolomonia"
echo ""
echo "VM_SSH_KEY (copy the exact format below):"
echo "=========================================="
cat github_vm_ssh_key
echo "=========================================="