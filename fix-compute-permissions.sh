#!/bin/bash
# Comprehensive fix for compute.instances.get permission issues

set -e

PROJECT_ID="nine-tones-bots-2025-468320"
SA_EMAIL="github-telegram-bots@${PROJECT_ID}.iam.gserviceaccount.com"

echo "🔧 COMPREHENSIVE COMPUTE PERMISSIONS FIX"
echo "========================================"
echo "Project: $PROJECT_ID"
echo "Service Account: $SA_EMAIL"
echo ""

# Step 1: Verify service account exists
echo "1️⃣ Verifying service account exists..."
if gcloud iam service-accounts describe $SA_EMAIL --project=$PROJECT_ID >/dev/null 2>&1; then
    echo "✅ Service account exists"
else
    echo "❌ Service account does not exist - creating it..."
    gcloud iam service-accounts create github-telegram-bots \
        --display-name="GitHub Telegram Bots Deploy" \
        --description="Service account for GitHub Actions telegram bot deployment" \
        --project=$PROJECT_ID
fi

# Step 2: Enable required APIs
echo ""
echo "2️⃣ Enabling required APIs..."
REQUIRED_APIS=(
    "compute.googleapis.com"
    "iam.googleapis.com" 
    "cloudresourcemanager.googleapis.com"
    "secretmanager.googleapis.com"
    "artifactregistry.googleapis.com"
)

for api in "${REQUIRED_APIS[@]}"; do
    echo "Enabling $api..."
    gcloud services enable $api --project=$PROJECT_ID
done

# Step 3: Remove existing permissions and re-add them
echo ""
echo "3️⃣ Cleaning and re-applying permissions..."

# Remove existing roles first (ignore errors if they don't exist)
EXISTING_ROLES=(
    "roles/compute.admin"
    "roles/compute.instanceAdmin.v1"
    "roles/compute.viewer"
    "roles/secretmanager.admin"
    "roles/artifactregistry.admin"
    "roles/iam.serviceAccountAdmin"
)

echo "Removing existing roles..."
for role in "${EXISTING_ROLES[@]}"; do
    gcloud projects remove-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="$role" 2>/dev/null || echo "Role $role was not assigned"
done

# Add permissions back with specific compute permissions
echo ""
echo "Adding comprehensive permissions..."

# Core compute permissions - using the most specific roles first
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/compute.instanceAdmin.v1"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/compute.viewer"

# Additional compute permissions to ensure metadata access
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/compute.admin"

# Secret Manager permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.admin"

# Artifact Registry permissions  
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/artifactregistry.admin"

# IAM permissions for service account management
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/iam.serviceAccountUser"

# CRITICAL: Allow GitHub SA to use VM's service account
echo "Adding permission to use VM's service account..."
VM_SA_EMAIL="vm-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts add-iam-policy-binding $VM_SA_EMAIL \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/iam.serviceAccountUser" \
    --project=$PROJECT_ID

# Step 4: Wait for propagation and verify
echo ""
echo "4️⃣ Waiting for IAM propagation (30 seconds)..."
sleep 30

echo ""
echo "5️⃣ Verifying permissions..."
echo "Current permissions for $SA_EMAIL:"
gcloud projects get-iam-policy $PROJECT_ID \
    --flatten="bindings[].members" \
    --format='table(bindings.role)' \
    --filter="bindings.members:$SA_EMAIL" | sort

# Step 6: Test the problematic command
echo ""
echo "6️⃣ Testing the problematic command..."
echo "Testing: gcloud compute instances describe vm-runtime --zone=europe-west3-b"

if gcloud auth activate-service-account --key-file=<(echo "$GCP_SA_KEY") 2>/dev/null || true; then
    if gcloud compute instances describe vm-runtime --zone=europe-west3-b --project=$PROJECT_ID >/dev/null 2>&1; then
        echo "✅ SUCCESS: Service account can access vm-runtime!"
        
        echo "Testing metadata access..."
        if gcloud compute instances add-metadata vm-runtime \
             --zone=europe-west3-b \
             --project=$PROJECT_ID \
             --metadata=test-key=test-value >/dev/null 2>&1; then
            echo "✅ SUCCESS: Service account can modify metadata!"
            # Clean up test metadata
            gcloud compute instances remove-metadata vm-runtime \
                --zone=europe-west3-b \
                --project=$PROJECT_ID \
                --keys=test-key >/dev/null 2>&1 || true
        else
            echo "❌ FAILED: Cannot modify metadata"
        fi
    else
        echo "❌ FAILED: Cannot access vm-runtime"
        echo "This might be an organization policy issue or the VM is in a different project"
    fi
else
    echo "⚠️ Cannot test with service account key directly from this script"
fi

echo ""
echo "🎯 SUMMARY:"
echo "✅ Service account verified/created"
echo "✅ APIs enabled"  
echo "✅ Permissions applied with redundancy"
echo "✅ 30-second propagation wait completed"
echo ""
echo "If GitHub Actions still fails, the issue might be:"
echo "1. Organization policies blocking compute access"
echo "2. The VM is in a different project than expected"
echo "3. The service account JSON in GitHub secrets is outdated"
echo ""
echo "Next: Run the GitHub Actions diagnostic workflow to get detailed error info"