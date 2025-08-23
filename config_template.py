#!/usr/bin/env python3
"""
Secure Configuration Template
Replace hardcoded credentials with this secure configuration approach.

NEVER commit actual credentials to version control!
"""

import os
from typing import Optional
import json
from pathlib import Path

class SecureConfig:
    """Secure configuration management with validation and environment variable support."""
    
    def __init__(self):
        self.telegram_token = self._get_telegram_token()
        self.openai_api_key = self._get_openai_key()
        self.google_credentials = self._get_google_credentials()
        self.sheet_config = self._get_sheet_config()
        
    def _get_telegram_token(self) -> str:
        """Get Telegram bot token from environment or raise error."""
        token = (
            os.environ.get('TELEGRAM_TOKEN_BOT') or 
            os.environ.get('ORDER_BOT_TOKEN') or
            os.environ.get('TELEGRAM_TOKEN')
        )
        
        if not token:
            raise ValueError(
                "Telegram bot token not found! Set one of these environment variables:\n"
                "- TELEGRAM_TOKEN_BOT\n"
                "- ORDER_BOT_TOKEN\n"
                "- TELEGRAM_TOKEN"
            )
        
        # Basic validation
        if len(token) < 20 or ':' not in token:
            raise ValueError("Invalid Telegram bot token format")
        
        return token
    
    def _get_openai_key(self) -> str:
        """Get OpenAI API key from environment."""
        key = os.environ.get('OPENAI_API_KEY')
        
        if not key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        # Basic validation
        if not key.startswith('sk-'):
            raise ValueError("Invalid OpenAI API key format")
        
        return key
    
    def _get_google_credentials(self) -> dict:
        """Get Google credentials from file or environment."""
        # Try environment variable first (for Docker)
        creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if creds_json:
            try:
                return json.loads(creds_json)
            except json.JSONDecodeError:
                raise ValueError("Invalid GOOGLE_CREDENTIALS_JSON format")
        
        # Try file path
        creds_file = os.environ.get('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
        if Path(creds_file).exists():
            with open(creds_file, 'r') as f:
                return json.load(f)
        
        raise ValueError(
            f"Google credentials not found! Either:\n"
            f"1. Set GOOGLE_CREDENTIALS_JSON environment variable with JSON content\n"
            f"2. Place credentials file at: {creds_file}\n"
            f"3. Set GOOGLE_CREDENTIALS_FILE to point to your credentials file"
        )
    
    def _get_sheet_config(self) -> dict:
        """Get Google Sheets configuration."""
        return {
            'sheet_name': os.environ.get('SHEET_NAME', '9_ტონა_ფული'),
            'worksheet_name': os.environ.get('WORKSHEET_NAME', 'Payments'),
            'sheet_id': os.environ.get('SHEET_ID'),  # Optional, for direct access
        }
    
    def validate(self) -> bool:
        """Validate all configuration is properly set."""
        try:
            # Test all properties to ensure they work
            _ = self.telegram_token
            _ = self.openai_api_key
            _ = self.google_credentials
            _ = self.sheet_config
            return True
        except Exception as e:
            print(f"Configuration validation failed: {e}")
            return False

# Usage example:
def create_secure_config() -> SecureConfig:
    """Create and validate secure configuration."""
    config = SecureConfig()
    
    if not config.validate():
        raise ValueError("Configuration validation failed")
    
    print("✅ Configuration loaded successfully")
    return config

# Environment setup instructions
def print_setup_instructions():
    """Print instructions for setting up environment variables."""
    print("""
🔐 SECURE CONFIGURATION SETUP INSTRUCTIONS

1. Create a .env file (NEVER commit this to git):
   ```
   # Telegram Bot Configuration
   TELEGRAM_TOKEN_BOT=your_telegram_bot_token_here
   
   # OpenAI Configuration  
   OPENAI_API_KEY=sk-your_openai_api_key_here
   
   # Google Sheets Configuration
   SHEET_NAME=9_ტონა_ფული
   WORKSHEET_NAME=Payments
   
   # Optional: Direct sheet access
   SHEET_ID=your_google_sheet_id_here
   ```

2. For Google Credentials, choose ONE of these methods:

   Method A - Credentials File (Recommended for local development):
   ```
   GOOGLE_CREDENTIALS_FILE=credentials.json
   ```
   
   Method B - Environment Variable (Recommended for Docker/Production):
   ```
   GOOGLE_CREDENTIALS_JSON='{"type": "service_account", "project_id": "...", ...}'
   ```

3. Load environment variables:
   
   For Python development:
   ```python
   from dotenv import load_dotenv
   load_dotenv()  # Load .env file
   ```
   
   For Docker:
   ```bash
   docker run --env-file .env your-bot-image
   ```
   
   For systemd service:
   ```ini
   [Service]
   EnvironmentFile=/path/to/.env
   ```

4. Security Checklist:
   ✅ .env file is in .gitignore
   ✅ credentials.json is in .gitignore  
   ✅ No hardcoded tokens in source code
   ✅ Environment variables are set correctly
   ✅ File permissions are restricted (600)

5. Testing Configuration:
   ```python
   from config_template import create_secure_config
   config = create_secure_config()
   print("Configuration is valid!")
   ```
""")

if __name__ == '__main__':
    print_setup_instructions()
    
    # Test configuration if environment is set up
    try:
        config = create_secure_config()
        print("🎉 Configuration test passed!")
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        print("\nRun this script again after setting up environment variables.")