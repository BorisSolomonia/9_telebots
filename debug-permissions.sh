#!/bin/bash
# Debug GCP Permissions and Resources

PROJECT_ID="nine-tones-bots-2025-468320"
SA_EMAIL="github-telegram-bots@${PROJECT_ID}.iam.gserviceaccount.com"
VM_NAME="telegram-bots-vm"
ZONE="europe-west3-a"

echo "🔍 DEBUGGING GCP PERMISSIONS AND RESOURCES"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Service Account: $SA_EMAIL"
echo "VM Name: $VM_NAME"
echo "Zone: $ZONE"
echo ""

# Check 1: Does the service account exist?
echo "1️⃣ Checking if service account exists..."
if gcloud iam service-accounts describe $SA_EMAIL --project=$PROJECT_ID >/dev/null 2>&1; then
    echo "✅ Service account exists"
else
    echo "❌ Service account does NOT exist"
fi
echo ""

# Check 2: What permissions does the service account have?
echo "2️⃣ Current service account permissions:"
gcloud projects get-iam-policy $PROJECT_ID \
    --flatten="bindings[].members" \
    --format='table(bindings.role)' \
    --filter="bindings.members:$SA_EMAIL"
echo ""

# Check 3: Does the VM exist?
echo "3️⃣ Checking if VM exists..."
if gcloud compute instances describe $VM_NAME --zone=$ZONE --project=$PROJECT_ID >/dev/null 2>&1; then
    echo "✅ VM exists"
    echo "VM Status:"
    gcloud compute instances describe $VM_NAME --zone=$ZONE --project=$PROJECT_ID --format="value(status)"
else
    echo "❌ VM does NOT exist or is in wrong zone"
    echo "Listing all VMs in project:"
    gcloud compute instances list --project=$PROJECT_ID
fi
echo ""

# Check 4: Test specific permission
echo "4️⃣ Testing compute.instances.get permission..."
if gcloud compute instances describe $VM_NAME --zone=$ZONE --project=$PROJECT_ID --impersonate-service-account=$SA_EMAIL >/dev/null 2>&1; then
    echo "✅ Service account CAN access the VM"
else
    echo "❌ Service account CANNOT access the VM"
fi
echo ""

# Check 5: List all required APIs
echo "5️⃣ Checking if required APIs are enabled..."
REQUIRED_APIS=(
    "compute.googleapis.com"
    "secretmanager.googleapis.com"
    "artifactregistry.googleapis.com"
    "iam.googleapis.com"
)

for api in "${REQUIRED_APIS[@]}"; do
    if gcloud services list --enabled --filter="name:$api" --format="value(name)" --project=$PROJECT_ID | grep -q "$api"; then
        echo "✅ $api is enabled"
    else
        echo "❌ $api is NOT enabled"
    fi
done
echo ""

# Check 6: Test metadata access
echo "6️⃣ Testing metadata access..."
if gcloud compute instances add-metadata $VM_NAME --zone=$ZONE --project=$PROJECT_ID --metadata=test-key=test-value --impersonate-service-account=$SA_EMAIL --dry-run >/dev/null 2>&1; then
    echo "✅ Service account CAN modify VM metadata"
else
    echo "❌ Service account CANNOT modify VM metadata"
fi
echo ""

echo "🎯 SUMMARY:"
echo "If any items above show ❌, that's likely the cause of your error."