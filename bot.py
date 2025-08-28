import logging
import asyncio
import json
from typing import Optional, Tuple, Dict
import os
import openai
import difflib
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import nest_asyncio
from pathlib import Path
# from dotenv import load_dotenv
# load_dotenv()  # Load environment variables from .env file
nest_asyncio.apply()

# GCP Secret Manager import (optional - only if needed)
try:
    from google.cloud import secretmanager
    GCP_AVAILABLE = True
except ImportError:
    logger.warning("google-cloud-secret-manager not available - GCP secret fetch disabled")
    GCP_AVAILABLE = False

# Config from env vars
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN_BOT']
OPENAI_API_KEY = os.environ['OPENAI_API_KEY']
SHEET_NAME = os.environ.get('SHEET_NAME', '9_ტონა_ფული')
WORKSHEET_NAME = os.environ.get('WORKSHEET_NAME', 'Payments')
CREDS_FILE = os.environ['CREDS_FILE']

# Validate API keys
if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise ValueError("TELEGRAM_TOKEN and OPENAI_API_KEY must be set")

# Initialize OpenAI
openai.api_key = OPENAI_API_KEY
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Google Sheets Setup
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
CREDS = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
CLIENT = gspread.authorize(CREDS)

# Logging setup - console only (Docker handles log collection)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class PaymentBot:
    """Simplified payment bot."""

    def __init__(self) -> None:
        self.customers: list[str] = []
        self.name_to_full: Dict[str, str] = {}
        self.project_id = "527887913788"
        self.secret_id = "customers-json"
        self.message_count = 0
        self._load_customers()

    def _load_customers(self) -> None:
        """Load customers from JSON or fetch from GCP secret if not found."""
        logger.info("CUSTOMER_LOADING: Starting customer data initialization...")
        customers_file = Path('customers.json')
        
        # First, try to load existing file
        if customers_file.exists():
            logger.info("CUSTOMER_LOADING: customers.json found, attempting to load...")
            if self._load_from_file():
                return  # Successfully loaded from file
        
        # If file doesn't exist or loading failed, try GCP secret (direct to memory)
        logger.info("CUSTOMER_LOADING: customers.json not found or failed to load, trying GCP Secret Manager...")
        if self._load_from_gcp_secret():
            return  # Successfully loaded from secret
        
        # Final fallback - empty list
        logger.error("CUSTOMER_LOADING: ❌ All methods failed, starting with empty customer list")
        self.customers = []
        self._build_name_mapping()
    
    def _load_from_file(self) -> bool:
        """Load customers from local customers.json file."""
        try:
            logger.info("CUSTOMER_LOADING: Reading customers.json...")
            with open('customers.json', 'r', encoding='utf-8') as f:
                self.customers = json.load(f)
            
            logger.info(f"CUSTOMER_LOADING: ✅ Successfully loaded customers.json")
            logger.info(f"CUSTOMER_LOADING: Found {len(self.customers)} total customer entries")
            
            # Log first few customers as sample
            if self.customers:
                sample_customers = self.customers[:3]
                logger.info(f"CUSTOMER_LOADING: Sample customers: {sample_customers}")
                self._build_name_mapping()
                return True
            else:
                logger.warning("CUSTOMER_LOADING: customers.json is empty")
                return False
            
        except FileNotFoundError:
            logger.warning("CUSTOMER_LOADING: customers.json file not found")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"CUSTOMER_LOADING: ❌ Invalid JSON in customers.json: {e}")
            return False
        except Exception as e:
            logger.error(f"CUSTOMER_LOADING: ❌ Error loading customers.json: {e}")
            return False
    
    def _load_from_gcp_secret(self) -> bool:
        """Load customers data directly from GCP Secret Manager to memory."""
        if not GCP_AVAILABLE:
            logger.error("CUSTOMER_LOADING: GCP Secret Manager library not available")
            return False
        
        try:
            logger.info(f"CUSTOMER_LOADING: Fetching from GCP secret: projects/{self.project_id}/secrets/{self.secret_id}")
            
            # Initialize client
            client = secretmanager.SecretManagerServiceClient()
            secret_name = f"projects/{self.project_id}/secrets/{self.secret_id}/versions/latest"
            
            logger.info(f"CUSTOMER_LOADING: Accessing secret: {secret_name}")
            response = client.access_secret_version(request={"name": secret_name})
            
            # Decode the secret payload
            secret_data = response.payload.data.decode("UTF-8")
            logger.info(f"CUSTOMER_LOADING: Retrieved secret data ({len(secret_data)} characters)")
            
            # Parse and validate JSON
            customers_data = json.loads(secret_data)
            
            if not isinstance(customers_data, list):
                logger.error(f"CUSTOMER_LOADING: Expected list, got {type(customers_data)}")
                return False
            
            logger.info(f"CUSTOMER_LOADING: Parsed {len(customers_data)} customer entries from secret")
            
            # Store directly in memory (no file write needed for read-only filesystem)
            self.customers = customers_data
            
            # Log first few customers as sample
            if self.customers:
                sample_customers = self.customers[:3]
                logger.info(f"CUSTOMER_LOADING: Sample customers from secret: {sample_customers}")
            
            logger.info("CUSTOMER_LOADING: ✅ Successfully loaded customer data from GCP secret to memory")
            
            # Build name mapping
            self._build_name_mapping()
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"CUSTOMER_LOADING: ❌ Invalid JSON in GCP secret: {e}")
            return False
        except Exception as e:
            logger.error(f"CUSTOMER_LOADING: ❌ Failed to fetch from GCP secret: {e}")
            logger.error("CUSTOMER_LOADING: Make sure VM has proper GCP permissions for Secret Manager")
            return False
    
    def _build_name_mapping(self):
        """Build customer name mapping from loaded customers list."""
        logger.info("CUSTOMER_LOADING: Building customer name mapping...")
        self.name_to_full = {}
        mapping_count = 0
        
        for customer in self.customers:
            customer = customer.strip()
            if customer:
                # Extract name from format: (code) name
                match = re.match(r'\((.*?)\)\s*(.*)', customer)
                if match:
                    name = match.group(2).strip()
                    if name:  # Only add non-empty names
                        self.name_to_full[name] = customer
                        mapping_count += 1
                else:
                    # Just use the whole string as name
                    self.name_to_full[customer] = customer
                    mapping_count += 1
        
        logger.info(f"CUSTOMER_LOADING: ✅ Created {mapping_count} customer name mappings")
        
        if mapping_count > 0:
            # Log sample mappings
            sample_mappings = dict(list(self.name_to_full.items())[:5])
            logger.info(f"CUSTOMER_LOADING: Sample mappings: {sample_mappings}")
        else:
            logger.warning("CUSTOMER_LOADING: ⚠️ No customer name mappings created!")

    def parse_payment(self, text: str) -> Optional[Tuple[str, float]]:
        """Parse payment text into name and amount.
        Format: customer_name amount [currency]
        """
        logger.info(f"PARSING: Attempting to parse message: '{text}'")
        
        # Pattern: name (any text) space amount (digits with optional decimal)
        pattern = r'^(.*)\s+(\d+(?:\.\d+)?)\s*(?:GEL|USD|EUR|ლარი|₾)?$'
        match = re.match(pattern, text.strip())
        
        if match:
            name = match.group(1).strip()
            amount_str = match.group(2).strip()
            logger.info(f"PARSING: Regex extracted - Customer name: '{name}', Amount: '{amount_str}'")
            
            try:
                amount = float(amount_str)
                if amount > 0:
                    logger.info(f"PARSING: Successfully parsed - Name: '{name}', Amount: {amount}")
                    return name, amount
                else:
                    logger.warning(f"PARSING: Amount must be positive, got: {amount}")
            except ValueError as e:
                logger.error(f"PARSING: Failed to convert amount '{amount_str}' to float: {e}")
        else:
            logger.warning(f"PARSING: Message '{text}' does not match expected format (name amount [currency])")
        
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def extract_payment_with_ai(self, text: str) -> Optional[Tuple[str, float]]:
        """Use OpenAI to extract customer name and amount when regex fails."""
        logger.info(f"OPENAI_EXTRACTION: Attempting AI-based payment extraction for: '{text}'")
        
        system_prompt = (
            "You are a payment message parser. Extract customer name and payment amount from Georgian/English text.\n"
            "Return ONLY a JSON object with 'name' and 'amount' fields, or 'null' if no valid payment found.\n"
            "Example: {\"name\": \"შპს მაგსი\", \"amount\": 150.5}\n"
            "Handle various formats: name+amount, amount+name, with/without currency symbols."
        )
        
        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract payment info: {text}"}
                ],
                max_tokens=100,
                temperature=0.1
            )
            
            result = response.choices[0].message.content.strip()
            usage = response.usage
            
            logger.info(f"OPENAI_EXTRACTION: GPT response: '{result}'")
            logger.info(f"OPENAI_EXTRACTION: Token usage - Prompt: {usage.prompt_tokens}, Completion: {usage.completion_tokens}, Total: {usage.total_tokens}")
            
            if result == "null":
                logger.info(f"OPENAI_EXTRACTION: GPT could not extract payment info from: '{text}'")
                return None
            
            # Parse JSON response
            try:
                data = json.loads(result)
                name = data.get('name', '').strip()
                amount = float(data.get('amount', 0))
                
                if name and amount > 0:
                    logger.info(f"OPENAI_EXTRACTION: Successfully extracted - Name: '{name}', Amount: {amount}")
                    return name, amount
                else:
                    logger.warning(f"OPENAI_EXTRACTION: Invalid extracted data - Name: '{name}', Amount: {amount}")
            
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                logger.error(f"OPENAI_EXTRACTION: Failed to parse GPT response '{result}': {e}")
            
            return None
            
        except Exception as e:
            logger.error(f"OPENAI_EXTRACTION: Error during AI extraction for '{text}': {e}")
            return None

    async def handle_new_customer_command(self, text: str, message, username: str) -> None:
        """Handle 'new:<customer name>' command to add new customer."""
        logger.info(f"NEW_CUSTOMER: Processing command from {username}: '{text}'")
        
        # Extract customer name from command
        try:
            customer_name = text[4:].strip()  # Remove 'new:' prefix
            if not customer_name:
                await message.reply_text("❌ მომხმარებლის სახელი არ არის მითითებული.\nგამოიყენეთ: new:კლიენტის სახელი")
                return
            
            logger.info(f"NEW_CUSTOMER: Attempting to add customer: '{customer_name}'")
            
            # Check if customer already exists
            if customer_name in self.customers:
                logger.info(f"NEW_CUSTOMER: Customer '{customer_name}' already exists")
                await message.reply_text(f"⚠️ კლიენტი '{customer_name}' უკვე არსებობს.")
                return
            
            # Add to local list
            self.customers.append(customer_name)
            
            # Update name mapping
            # Extract name from format: (code) name or just use full name
            match = re.match(r'\((.*?)\)\s*(.*)', customer_name)
            if match:
                short_name = match.group(2).strip()
                if short_name:
                    self.name_to_full[short_name] = customer_name
            else:
                self.name_to_full[customer_name] = customer_name
            
            logger.info(f"NEW_CUSTOMER: Added '{customer_name}' to local list ({len(self.customers)} total customers)")
            
            # Update GCP secret
            success = await self.update_gcp_secret()
            
            if success:
                await message.reply_text(f"✅ კლიენტი დამატებულია:\n{customer_name}\n\nსულ კლიენტები: {len(self.customers)}")
                logger.info(f"NEW_CUSTOMER: Successfully added '{customer_name}' and updated GCP secret")
            else:
                # Remove from local list if GCP update failed
                self.customers.remove(customer_name)
                if customer_name in self.name_to_full:
                    del self.name_to_full[customer_name]
                if match and short_name in self.name_to_full:
                    del self.name_to_full[short_name]
                
                await message.reply_text(f"❌ კლიენტის დამატება ვერ მოხერხდა.\nGCP Secret Manager-ის განახლება ვერ მოხერხდა.")
                logger.error(f"NEW_CUSTOMER: Failed to update GCP secret, removed '{customer_name}' from local list")
                
        except Exception as e:
            logger.error(f"NEW_CUSTOMER: Error processing command '{text}': {e}")
            await message.reply_text("❌ კლიენტის დამატებისას მოხდა შეცდომა. გთხოვთ სცადოთ მოგვიანებით.")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def update_gcp_secret(self) -> bool:
        """Update GCP secret with current customer list."""
        if not GCP_AVAILABLE:
            logger.error("UPDATE_SECRET: GCP Secret Manager library not available")
            return False
        
        try:
            logger.info(f"UPDATE_SECRET: Updating GCP secret with {len(self.customers)} customers")
            
            # Initialize client
            client = secretmanager.SecretManagerServiceClient()
            parent = f"projects/{self.project_id}/secrets/{self.secret_id}"
            
            # Prepare the new secret data
            secret_data = json.dumps(self.customers, ensure_ascii=False, indent=2)
            
            logger.info(f"UPDATE_SECRET: Secret data size: {len(secret_data)} characters")
            
            # Add a new version to the secret
            response = client.add_secret_version(
                request={
                    "parent": parent,
                    "payload": {"data": secret_data.encode("UTF-8")}
                }
            )
            
            logger.info(f"UPDATE_SECRET: ✅ Successfully created new secret version: {response.name}")
            return True
            
        except Exception as e:
            logger.error(f"UPDATE_SECRET: ❌ Failed to update GCP secret: {e}")
            return False

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages - simplified flow."""
        message = update.message or update.edited_message
        if not message or not message.text:
            return

        # Increment message counter for tracking
        self.message_count += 1

        text = message.text
        username = message.from_user.username or f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
        source = 'Edited' if update.edited_message else 'Direct'

        logger.info(f"Processing message from {username}: '{text}'")

        # Check for commands first
        if text.startswith('new:'):
            await self.handle_new_customer_command(text, message, username)
            return

        # Parse the payment
        parsed = self.parse_payment(text)
        if not parsed:
            # Try OpenAI as fallback for parsing
            logger.info(f"FALLBACK: Regex parsing failed, attempting OpenAI extraction for: '{text}'")
            ai_parsed = await self.extract_payment_with_ai(text)
            if ai_parsed:
                name, amount = ai_parsed
                logger.info(f"FALLBACK: OpenAI successfully extracted - Name: '{name}', Amount: {amount}")
            else:
                logger.warning(f"FALLBACK: OpenAI also failed to parse: '{text}'")
                return
        else:
            name, amount = parsed
            logger.info(f"PARSING RESULT: Successfully parsed payment - Customer: '{name}', Amount: {amount}")

        # Try to find customer
        customer_full = await self.find_customer(name)
        
        if customer_full:
            # Record the payment
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            success = await self.record_to_sheets(timestamp, customer_full, str(amount), source, username)
            
            if success:
                await message.reply_text(f"✅ გადახდა ჩაწერილია:\n{customer_full}\nთანხა: {amount} ₾")
                logger.info(f"Payment recorded: {customer_full} {amount} by {username}")
            else:
                await message.reply_text("❌ ვერ მოხერხდა ჩაწერა Google Sheets-ში. გთხოვთ სცადოთ მოგვიანებით.")
        else:
            await message.reply_text(f"❌ კლიენტი '{name}' ვერ მოიძებნა.\nგთხოვთ გადაამოწმოთ სახელი და სცადოთ თავიდან.")
            logger.warning(f"Customer not found: '{name}'")

    async def find_customer(self, name: str) -> Optional[str]:
        """Find customer by name - first direct match, then GPT if needed."""
        logger.info(f"CUSTOMER_SEARCH: Starting search for customer: '{name}'")
        logger.info(f"CUSTOMER_SEARCH: Available customers: {len(self.customers)} total, {len(self.name_to_full)} mapped names")
        
        if len(self.customers) == 0:
            logger.error("CUSTOMER_SEARCH: ❌ No customers loaded! Cannot perform search.")
            logger.error("CUSTOMER_SEARCH: Check if customers.json exists and contains valid data")
            return None
        
        # Step 1: Check for direct match
        if name in self.name_to_full:
            logger.info(f"CUSTOMER_SEARCH: Direct match found - '{name}' -> '{self.name_to_full[name]}'")
            return self.name_to_full[name]
        
        # Step 2: Check if it's already a full customer string
        if name in self.customers:
            logger.info(f"CUSTOMER_SEARCH: Full customer string provided: '{name}'")
            return name
        
        # Step 3: Case-insensitive search
        name_lower = name.lower()
        for short_name, full_name in self.name_to_full.items():
            if short_name.lower() == name_lower:
                logger.info(f"CUSTOMER_SEARCH: Case-insensitive match found - '{name}' -> '{full_name}'")
                return full_name
        
        # Step 4: Try partial matching (substring search)
        name_lower = name.lower()
        partial_matches = []
        for short_name, full_name in self.name_to_full.items():
            if name_lower in short_name.lower() or short_name.lower() in name_lower:
                partial_matches.append((short_name, full_name))
        
        if partial_matches:
            logger.info(f"CUSTOMER_SEARCH: Partial matches found for '{name}': {[match[0] for match in partial_matches]}")
            # If only one partial match, use it
            if len(partial_matches) == 1:
                best_match = partial_matches[0][1]
                logger.info(f"CUSTOMER_SEARCH: Using single partial match: '{name}' -> '{best_match}'")
                return best_match
            else:
                # Multiple matches, log them but continue to GPT
                logger.info(f"CUSTOMER_SEARCH: Multiple partial matches, will try GPT: {[match[0] for match in partial_matches]}")
        
        # Step 5: Find closest matches for logging
        customer_names = list(self.name_to_full.keys())
        closest_matches = difflib.get_close_matches(name, customer_names, n=5, cutoff=0.3)
        
        if closest_matches:
            logger.info(f"CUSTOMER_SEARCH: No exact match found. Closest matches for '{name}': {closest_matches}")
            # Also log the full customer names for the closest matches
            closest_full = [f"'{match}' -> '{self.name_to_full[match]}'" for match in closest_matches]
            logger.info(f"CUSTOMER_SEARCH: Closest full customer entries: {closest_full}")
        else:
            logger.warning(f"CUSTOMER_SEARCH: No close matches found for '{name}' (using cutoff 0.3)")
        
        # Step 6: Use GPT to try to map the name
        logger.info(f"CUSTOMER_SEARCH: No direct/partial match for '{name}', trying GPT mapping...")
        gpt_result = await self.map_customer_with_gpt(name)
        
        if gpt_result:
            logger.info(f"CUSTOMER_SEARCH: GPT successfully mapped '{name}' -> '{gpt_result}'")
            return gpt_result
        
        logger.warning(f"CUSTOMER_SEARCH: Could not find customer '{name}' through any method")
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def map_customer_with_gpt(self, customer_name: str) -> Optional[str]:
        """Use GPT to map customer name to exact match from list."""
        logger.info(f"OPENAI_MAPPING: Starting GPT customer mapping for: '{customer_name}'")
        
        if not self.customers:
            logger.warning("OPENAI_MAPPING: No customers loaded, cannot perform mapping")
            return None
        
        # Get closest matches to reduce list size for GPT
        customer_names = list(self.name_to_full.keys())
        closest_matches = difflib.get_close_matches(customer_name, customer_names, n=20, cutoff=0.2)
        
        # Get full customer entries for closest matches
        if closest_matches:
            relevant_customers = [self.name_to_full[name] for name in closest_matches]
            logger.info(f"OPENAI_MAPPING: Using {len(closest_matches)} closest matches as context: {closest_matches}")
        else:
            # Use first 30 customers if no close matches
            relevant_customers = self.customers[:30]
            logger.info(f"OPENAI_MAPPING: No close matches found, using first {len(relevant_customers)} customers as context")
        
        logger.info(f"OPENAI_MAPPING: Sending {len(relevant_customers)} customer entries to GPT for context")
        
        system_prompt = (
            "You are a customer name mapping assistant. Map the input name to the EXACT customer from the list.\n"
            "Handle typos, abbreviations, and variations.\n"
            "Return ONLY the exact customer string from the list, or 'null' if no match.\n\n"
            f"CUSTOMERS:\n{json.dumps(relevant_customers, ensure_ascii=False)}"
        )
        
        user_message = f"Find customer: {customer_name}"
        logger.info(f"OPENAI_MAPPING: Sending request to GPT-3.5-turbo with message: '{user_message}'")
        
        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=100,
                temperature=0.1
            )
            
            result = response.choices[0].message.content.strip()
            usage = response.usage
            
            logger.info(f"OPENAI_MAPPING: GPT response received: '{result}'")
            logger.info(f"OPENAI_MAPPING: Token usage - Prompt: {usage.prompt_tokens}, Completion: {usage.completion_tokens}, Total: {usage.total_tokens}")
            
            # Verify the result is in our customer list
            if result != "null" and result in self.customers:
                logger.info(f"OPENAI_MAPPING: GPT mapping successful! '{customer_name}' -> '{result}'")
                return result
            elif result == "null":
                logger.info(f"OPENAI_MAPPING: GPT could not find a match for '{customer_name}' (returned 'null')")
            else:
                logger.warning(f"OPENAI_MAPPING: GPT returned invalid result '{result}' - not found in customer list")
            
            return None
            
        except Exception as e:
            logger.error(f"OPENAI_MAPPING: GPT mapping error for '{customer_name}': {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def record_to_sheets(self, timestamp: str, customer: str, amount: str, source: str, sender: str) -> bool:
        """Record payment to Google Sheets."""
        try:
            sheet = CLIENT.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
            row = [timestamp, customer, amount, source, sender]
            sheet.append_row(row)
            logger.info(f"Recorded to Sheets: {row}")
            return True
        except Exception as e:
            logger.error(f"Error recording to Sheets: {e}")
            return False

async def main() -> None:
    """Main bot setup and run."""
    logger.info("BOT_STARTUP: Starting Payment Bot (Docker handles log management)")
    
    bot = PaymentBot()
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Single message handler
    async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await bot.handle_message(update, context)
    
    # Add handler for text messages (including edited)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    logger.info("Bot started. Waiting for messages...")
    
    # Run the bot
    await application.run_polling()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}")