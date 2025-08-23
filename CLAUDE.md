# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Structure

This is a collection of Python-based Telegram bots for order management and payment processing. The repository contains multiple bot applications with different purposes:

### Main Bot Files
- `bot.py` - Core payment processing bot (primary bot)
- `order_bot.py` - Advanced order processing bot with GPT integration and customer management
- `order_bot_backup.py`, `order_bot_fixed.py` - Backup versions of the order bot
- `payment-bot/app.py` - Simplified payment bot (containerized version)
- `order-bot/orderapp.py` - Order bot for container deployment

### Bot Architecture

#### Payment Bot (`bot.py`)
- Simplified payment processing system
- Customer lookup with GPT fallback
- Google Sheets integration for payment logging
- Basic customer name mapping with fuzzy matching

#### Order Bot (`order_bot.py`)
- Advanced order processing with structured customer management
- GPT-3.5-turbo integration for order parsing and customer mapping
- Comprehensive error handling and retry mechanisms
- Async file I/O for customer data management
- Inline keyboard support for customer addition workflow
- Rate limiting and message flood control
- Session management for pending orders

### Key Components

1. **Customer Management**
   - Customer data stored in `customers.json` as array of full customer names
   - Format: `"(tax_id) Customer Name"` or just `"Customer Name"`
   - Automatic mapping of short names to full customer entries

2. **Order Processing Pipeline**
   - Text parsing using regex patterns
   - GPT integration for complex order interpretation
   - Customer name matching with fuzzy logic
   - Google Sheets integration for order logging

3. **Google Sheets Integration**
   - Uses service account credentials (`credentials.json`)
   - Records: timestamp, customer, amount, product, sender
   - Configurable sheet and worksheet names via environment variables

## Environment Variables

### Required
- `TELEGRAM_TOKEN_BOT` / `ORDER_BOT_TOKEN` - Telegram bot token
- `OPENAI_API_KEY` - OpenAI API key for GPT integration
- `CREDS_FILE` - Path to Google Sheets service account JSON file

### Optional
- `SHEET_NAME` - Google Sheets spreadsheet name (default: "9_ტონა_ფული")
- `WORKSHEET_NAME` - Worksheet name (default: "Payments")
- `CUSTOMERS_FILE` - Customer data file path (default: "customers.json")
- `MESSAGE_COOLDOWN` - Rate limiting in seconds (default: 5)
- `PENDING_ORDER_TIMEOUT` - Pending order timeout in seconds (default: 300)
- `MAX_RETRIES` - Maximum retry attempts (default: 3)

## Common Development Commands

### Running the Bots
```bash
# Main payment bot
python bot.py

# Advanced order bot
python order_bot.py

# Install dependencies
pip install -r requirements.txt
```

### Docker Deployment
```bash
# Build payment bot container
cd payment-bot
docker build -t payment-bot .

# Build order bot container  
cd order-bot
docker build -t order-bot .

# Run with environment variables
docker run -d --restart=always \
  -e ORDER_BOT_TOKEN="your-token" \
  -e OPENAI_API_KEY="your-key" \
  -e SHEETS_CREDS="$(cat credentials.json)" \
  -e CUSTOMERS_JSON="$(cat customers.json)" \
  --name bot-container \
  bot-image
```

### GCP Deployment
The repository includes comprehensive GCP deployment documentation in `DEPLOY.md` covering VM setup, Docker deployment, and container management.

## Testing

No formal test framework is configured. Testing is done manually by:
1. Sending test messages to the bot via Telegram
2. Checking Google Sheets for proper logging
3. Monitoring Docker logs for error handling

## Key Libraries

- `python-telegram-bot[callback-data]` - Telegram bot framework
- `openai` - GPT integration for order parsing
- `gspread` - Google Sheets API integration
- `oauth2client` - Google API authentication
- `tenacity` - Retry mechanisms for API calls
- `nest_asyncio` - Async compatibility
- `aiofiles` - Async file operations

## Architecture Patterns

1. **Retry Mechanisms** - All external API calls use tenacity for automatic retry on failures
2. **Rate Limiting** - Message flood control to prevent spam
3. **Async Operations** - Heavy use of asyncio for non-blocking operations
4. **Configuration Classes** - Environment variables managed through Config classes
5. **Error Recovery** - Comprehensive exception handling with graceful fallbacks
6. **State Management** - In-memory tracking of pending orders and user sessions

## Customer Data Format

Customer entries in `customers.json` follow this pattern:
```json
[
  "(405135946-დღგ) შპს მაგსი",
  "(62004022906) ბაჩუკი უშხვანი",
  "Simple Customer Name"
]
```

The bot automatically maps short names (e.g., "მაგსი", "ბაჩუკი") to full entries for order processing.

## Order Message Formats

Supported order formats:
- `შპს მაგსი 20 საქონლის ბარკალი`
- `ბაჩუკი 15 GEL ხორცი`  
- `Customer Name 10 kg Product`

The system handles Georgian and English text, various units (GEL, kg, ლარი, კგ), and flexible formatting.

## GCP Deployment Infrastructure

The project includes comprehensive GCP deployment setup with:

### Infrastructure Components
- **Caddy Reverse Proxy** - SSL termination and routing (`infra/caddy/`)
- **Docker Compose** - Multi-container orchestration (`secure-docker-setup/`)
- **GitHub Actions** - Automated CI/CD pipeline (`.github/workflows/deploy-gcp-production.yml`)
- **Secret Manager** - Secure credential storage
- **Artifact Registry** - Docker image repository

### Deployment Commands
```bash
# Complete GCP setup (run once)
chmod +x setup-gcp-deployment.sh
./setup-gcp-deployment.sh

# Manual deployment
./secure-deployment.sh deploy

# Health checks
./secure-deployment.sh health

# Rollback if needed
./secure-deployment.sh rollback
```

### Network Architecture
- `web` network - External access via Caddy
- `bot_internal` network - Internal service communication
- Health endpoints at `/health`, `/health/bot`, `/health/caddy`

### Security Features
- Non-root containers with security scanning
- Secret management via GCP Secret Manager
- SSL/TLS with automatic certificate management
- Rate limiting and security headers
- Container image signing with Cosign

### Files Created for Production Deployment
- `improved_order_bot.py` - Enhanced bot with caching and security
- `config_template.py` - Secure configuration management
- `infra/caddy/` - Reverse proxy configuration
- `secure-docker-setup/` - Production Docker setup
- `.github/workflows/deploy-gcp-production.yml` - Automated deployment
- `SECURITY_AND_IMPROVEMENT_ANALYSIS.md` - Security analysis and fixes

### Critical Security Fixes Applied
1. **Removed hardcoded credentials** from `examp` file
2. **Implemented file locking** for customer data consistency  
3. **Added GPT response caching** to reduce costs
4. **Enhanced error handling** with structured logging
5. **Implemented graceful shutdown** handling
6. **Added comprehensive health checks**