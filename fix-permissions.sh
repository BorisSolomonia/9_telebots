#!/bin/bash
# Fix GCP Service Account Permissions for GitHub Actions

set -e

PROJECT_ID="${GCP_PROJECT_ID:-nine-tones-bots-2025-468320}"
SA_EMAIL="github-deploy@${PROJECT_ID}.iam.gserviceaccount.com"

echo "🔧 Fixing GCP Service Account Permissions"
echo "Project: $PROJECT_ID"
echo "Service Account: $SA_EMAIL"
echo "=================================="

# Set project
gcloud config set project $PROJECT_ID

echo "📝 Adding required permissions..."

# Core compute permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/compute.instanceAdmin.v1"

# Specific permissions needed
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/compute.viewer"

# Secret Manager access
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor"

# Artifact Registry
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/artifactregistry.writer"

# Service Account usage
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/iam.serviceAccountUser"

# OS Login (for SSH if needed)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/compute.osLogin"

echo "✅ All permissions have been added!"
echo ""
echo "📋 Permissions Summary:"
echo "- compute.instanceAdmin.v1: Full VM management"
echo "- compute.viewer: Read VM information" 
echo "- secretmanager.secretAccessor: Access secrets"
echo "- artifactregistry.writer: Push Docker images"
echo "- iam.serviceAccountUser: Use service account"
echo "- compute.osLogin: SSH access if needed"
echo ""
echo "🚀 Your GitHub Actions workflow should now work!"