#!/usr/bin/env python3
"""
Create credentials.json from environment variables at runtime.
This handles the case where Google Sheets credentials are provided as environment variables
rather than files, which is common in containerized deployments.
"""

import os
import json
from pathlib import Path


def create_credentials_file():
    """Create credentials.json from environment variables if it doesn't exist."""
    
    # Check if credentials.json already exists
    creds_file = Path("credentials.json")
    if creds_file.exists():
        print("✅ credentials.json already exists")
        return True
    
    # Try to find credentials in environment variables
    possible_env_vars = [
        'GOOGLE_CREDENTIALS',
        'SHEETS_CREDS', 
        'GCP_SA_KEY',
        'SERVICE_ACCOUNT_KEY',
        'GOOGLE_SERVICE_ACCOUNT'
    ]
    
    credentials_json = None
    used_var = None
    
    for env_var in possible_env_vars:
        credentials_json = os.environ.get(env_var)
        if credentials_json:
            used_var = env_var
            break
    
    if not credentials_json:
        print("❌ No Google Sheets credentials found in environment variables")
        print(f"Looked for: {', '.join(possible_env_vars)}")
        return False
    
    try:
        # Parse to validate it's proper JSON
        creds_dict = json.loads(credentials_json)
        
        # Validate it looks like a service account key
        required_fields = ['type', 'project_id', 'private_key', 'client_email']
        if not all(field in creds_dict for field in required_fields):
            print(f"❌ Credentials from {used_var} missing required fields: {required_fields}")
            return False
        
        # Write to file
        with open("credentials.json", "w") as f:
            json.dump(creds_dict, f, indent=2)
        
        # Set secure permissions
        os.chmod("credentials.json", 0o600)
        
        print(f"✅ Created credentials.json from {used_var}")
        print(f"✅ Service account: {creds_dict.get('client_email', 'unknown')}")
        print(f"✅ Project ID: {creds_dict.get('project_id', 'unknown')}")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in {used_var}: {e}")
        return False
    except Exception as e:
        print(f"❌ Error creating credentials file: {e}")
        return False


if __name__ == "__main__":
    success = create_credentials_file()
    exit(0 if success else 1)