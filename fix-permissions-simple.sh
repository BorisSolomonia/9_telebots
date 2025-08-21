#!/bin/bash
# Simplified GCP Service Account Permissions (using broader roles)

set -e

PROJECT_ID="${GCP_PROJECT_ID:-nine-tones-bots-2025-468320}"
SA_EMAIL="github-deploy@${PROJECT_ID}.iam.gserviceaccount.com"

echo "🔧 Adding Simplified Permissions (Broader Roles)"
echo "Project: $PROJECT_ID"
echo "Service Account: $SA_EMAIL"
echo "=================================="

# Set project
gcloud config set project $PROJECT_ID

echo "📝 Adding broad permissions for deployment..."

# Compute Engine Admin (covers all VM operations)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/compute.admin"

# Secret Manager Admin
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.admin"

# Artifact Registry Admin  
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/artifactregistry.admin"

# Service Account Admin (for using service accounts)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/iam.serviceAccountAdmin"

echo "✅ Broad permissions added!"
echo ""
echo "⚠️  NOTE: These are broad admin roles for simplicity."
echo "   For production, consider using more specific roles."
echo ""
echo "📋 Roles Added:"
echo "- roles/compute.admin: Full Compute Engine access"
echo "- roles/secretmanager.admin: Full Secret Manager access"
echo "- roles/artifactregistry.admin: Full Artifact Registry access"
echo "- roles/iam.serviceAccountAdmin: Service account management"
echo ""
echo "🚀 GitHub Actions should now have all required permissions!"