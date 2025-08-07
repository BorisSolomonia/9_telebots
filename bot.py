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
# from dotenv import load_dotenv
# load_dotenv()  # Load environment variables from .env file
nest_asyncio.apply()

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

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class PaymentBot:
    """Simplified payment bot."""

    def __init__(self) -> None:
        self.customers: list[str] = []
        self.name_to_full: Dict[str, str] = {}
        self._load_customers()

    def _load_customers(self) -> None:
        """Load customers from JSON or initialize with defaults."""
        try:
            with open('customers.json', 'r', encoding='utf-8') as f:
                self.customers = json.load(f)
            logger.info(f"Loaded {len(self.customers)} customers from customers.json")
        except (FileNotFoundError, json.JSONDecodeError):
            # Initialize with empty list or default customers
            self.customers = []
            logger.warning("No customers.json found, starting with empty customer list")
        
        # Build name mapping
        for customer in self.customers:
            customer = customer.strip()
            if customer:
                # Extract name from format: (code) name
                match = re.match(r'\((.*?)\)\s*(.*)', customer)
                if match:
                    name = match.group(2).strip()
                    self.name_to_full[name] = customer
                else:
                    # Just use the whole string as name
                    self.name_to_full[customer] = customer

    def parse_payment(self, text: str) -> Optional[Tuple[str, float]]:
        """Parse payment text into name and amount.
        Format: customer_name amount [currency]
        """
        # Pattern: name (any text) space amount (digits with optional decimal)
        pattern = r'^(.*)\s+(\d+(?:\.\d+)?)\s*(?:GEL|USD|EUR)?$'
        match = re.match(pattern, text.strip())
        
        if match:
            name = match.group(1).strip()
            try:
                amount = float(match.group(2))
                if amount > 0:
                    return name, amount
            except ValueError:
                pass
        return None

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages - simplified flow."""
        message = update.message or update.edited_message
        if not message or not message.text:
            return

        text = message.text
        username = message.from_user.username or f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
        source = 'Edited' if update.edited_message else 'Direct'

        logger.info(f"Processing message from {username}: '{text}'")

        # Parse the payment
        parsed = self.parse_payment(text)
        if not parsed:
            # Not a valid payment format, ignore
            logger.debug(f"Could not parse payment from: '{text}'")
            return

        name, amount = parsed
        logger.info(f"Parsed payment: {name} -> {amount}")

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
        # Step 1: Check for direct match
        if name in self.name_to_full:
            logger.info(f"Direct match found: '{name}'")
            return self.name_to_full[name]
        
        # Step 2: Check if it's already a full customer string
        if name in self.customers:
            logger.info(f"Full customer string provided: '{name}'")
            return name
        
        # Step 3: Case-insensitive search
        name_lower = name.lower()
        for short_name, full_name in self.name_to_full.items():
            if short_name.lower() == name_lower:
                logger.info(f"Case-insensitive match found: '{name}' -> '{full_name}'")
                return full_name
        
        # Step 4: Use GPT to try to map the name
        logger.info(f"No direct match for '{name}', trying GPT mapping...")
        gpt_result = await self.map_customer_with_gpt(name)
        
        if gpt_result:
            logger.info(f"GPT successfully mapped: '{name}' -> '{gpt_result}'")
            return gpt_result
        
        logger.warning(f"Could not find customer: '{name}'")
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def map_customer_with_gpt(self, customer_name: str) -> Optional[str]:
        """Use GPT to map customer name to exact match from list."""
        if not self.customers:
            return None
        
        # Get closest matches to reduce list size for GPT
        customer_names = list(self.name_to_full.keys())
        closest_matches = difflib.get_close_matches(customer_name, customer_names, n=20, cutoff=0.2)
        
        # Get full customer entries for closest matches
        if closest_matches:
            relevant_customers = [self.name_to_full[name] for name in closest_matches]
        else:
            # Use first 30 customers if no close matches
            relevant_customers = self.customers[:30]
        
        system_prompt = (
            "You are a customer name mapping assistant. Map the input name to the EXACT customer from the list.\n"
            "Handle typos, abbreviations, and variations.\n"
            "Return ONLY the exact customer string from the list, or 'null' if no match.\n\n"
            f"CUSTOMERS:\n{json.dumps(relevant_customers, ensure_ascii=False)}"
        )
        
        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Find customer: {customer_name}"}
                ],
                max_tokens=100,
                temperature=0.1
            )
            
            result = response.choices[0].message.content.strip()
            
            # Verify the result is in our customer list
            if result != "null" and result in self.customers:
                return result
            
            return None
            
        except Exception as e:
            logger.error(f"GPT mapping error: {e}")
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