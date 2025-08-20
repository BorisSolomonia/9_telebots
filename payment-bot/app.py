import json
import os
import logging
import asyncio
from typing import Optional, Tuple, Dict
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
import traceback

nest_asyncio.apply()

# Initialize logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Config from env vars
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_BOT")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SHEETS_CREDS = os.environ.get("SHEETS_CREDS", "credentials.json")
CUSTOMERS_JSON = os.environ.get("CUSTOMERS_JSON")
SHEET_NAME = os.environ.get("SHEET_NAME", "9_ტონა_ფული")
SHEET_ID = os.environ.get("SHEET_ID")  # Optional: Use spreadsheet ID for reliability
WORKSHEET_NAME = os.environ.get("WORKSHEET_NAME", "Payments")

# Validate required env vars
if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    logger.error("Missing required environment variables: TELEGRAM_TOKEN_BOT and/or OPENAI_API_KEY")
    raise ValueError("TELEGRAM_TOKEN_BOT and OPENAI_API_KEY must be set")

try:
    openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
    logger.info("OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {str(e)}")
    raise

SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# Handle SHEETS_CREDS - either JSON string or file
try:
    if os.path.exists(SHEETS_CREDS):
        with open(SHEETS_CREDS, 'r', encoding='utf-8') as f:
            creds_data = json.load(f)
    else:
        creds_data = json.loads(SHEETS_CREDS)
    CREDS = ServiceAccountCredentials.from_json_keyfile_dict(creds_data, SCOPE)
    CLIENT = gspread.authorize(CREDS)
except Exception as e:
    logger.error(f"Failed to load Google Sheets credentials: {str(e)}")
    raise

class PaymentBot:
    def __init__(self) -> None:
        self.customers: list[str] = []
        self.name_to_full: Dict[str, str] = {}
        self.admins = ["Boris Solomonia", "Giorgi შავერდაშვილი", "Shota Gabilaia"]
        self._load_customers()

    def _load_customers(self) -> None:
        self.customers = []
        if CUSTOMERS_JSON:
            try:
                self.customers = json.loads(CUSTOMERS_JSON)
                logger.info(f"Loaded {len(self.customers)} customers from CUSTOMERS_JSON env var")
            except Exception as e:
                logger.warning(f"Failed to load customers from CUSTOMERS_JSON env var: {e}")
        if not self.customers:
            try:
                with open('customers.json', 'r', encoding='utf-8') as f:
                    self.customers = json.load(f)
                logger.info(f"Loaded {len(self.customers)} customers from customers.json file")
            except Exception as e:
                logger.warning(f"Failed to load customers from customers.json file: {e}. Starting with empty list.")

        for customer in self.customers:
            customer = customer.strip()
            if customer:
                match = re.match(r'\((.*?)\)\s*(.*)', customer)
                if match:
                    name = match.group(2).strip()
                    self.name_to_full[name] = customer
                else:
                    self.name_to_full[customer] = customer

    def add_customer(self, new_customer: str) -> None:
        new_customer = new_customer.strip()
        if new_customer and new_customer not in self.customers:
            self.customers.append(new_customer)
            match = re.match(r'\((.*?)\)\s*(.*)', new_customer)
            if match:
                name = match.group(2).strip()
                self.name_to_full[name] = new_customer
            else:
                self.name_to_full[new_customer] = new_customer
            try:
                with open('customers.json', 'w', encoding='utf-8') as f:
                    json.dump(self.customers, f, ensure_ascii=False, indent=4)
                logger.info(f"Added new customer: '{new_customer}' and saved to customers.json")
            except Exception as e:
                logger.error(f"Failed to save new customer to file: {str(e)}")

    def parse_payment(self, text: str) -> Optional[Tuple[str, float]]:
        # Remove years (e.g., "2015") from name
        cleaned_text = re.sub(r'\b\d{4}\b', '', text).strip()
        pattern = r'^(.*)\s+(\d+(?:\.\d+)?)\s*(?:GEL|USD|EUR)?$'
        match = re.match(pattern, cleaned_text)
        
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
        message = update.message or update.edited_message
        if not message or not message.text:
            return

        text = message.text
        from_user = message.from_user
        sender_name = f"{from_user.first_name or ''} {from_user.last_name or ''}".strip()
        source = 'Edited' if update.edited_message else 'Direct'

        logger.info(f"Processing message from {sender_name}: '{text}'")

        # Check if this is a new customer addition (starts with "new ")
        if sender_name in self.admins and text.lower().startswith("new "):
            new_customer = text[4:].strip()  # Remove "new " prefix
            self.add_customer(new_customer)
            await message.reply_text(f"✅ კლიენტი დამატებულია: {new_customer}")
            return

        # Check if this is a reply from admin to add customer
        if sender_name in self.admins and message.reply_to_message:
            reply_msg = message.reply_to_message
            if reply_msg.from_user.is_bot and "ვერ მოიძებნა" in reply_msg.text:
                new_customer = text.strip()
                self.add_customer(new_customer)
                await message.reply_text(f"✅ კლიენტი დამატებულია: {new_customer}")
                return

        parsed = self.parse_payment(text)
        if not parsed:
            return

        name, amount = parsed
        logger.info(f"Parsed payment: {name} -> {amount}")

        customer_full = await self.find_customer(name)
        
        if customer_full:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            success = await self.record_to_sheets(timestamp, customer_full, str(amount), source, sender_name)
            
            if success:
                await message.reply_text(f"✅ გადახდა ჩაწერილია:\n{customer_full}\nთანხა: {amount} ₾")
                logger.info(f"Payment recorded: {customer_full} {amount} by {sender_name}")
            else:
                await message.reply_text("❌ ვერ მოხერხდა ჩაწერა Google Sheets-ში. გთხოვთ გადაამოწმოთ Spreadsheet ID ან Sheet-ის სახელი.")
        else:
            await message.reply_text(f"❌ კლიენტი '{name}' ვერ მოიძებნა.\n@BorisSolomonia @Giorgiშავერდაშვილი @ShotaGabilaia, გთხოვთ დაამატოთ ახალი კლიენტი (უპასუხეთ ამ შეტყობინებას სრული სახელით ან გამოიყენეთ 'new <სახელი>').")
            logger.warning(f"Customer not found: '{name}'")

    async def find_customer(self, name: str) -> Optional[str]:
        # Direct match
        if name in self.name_to_full:
            logger.info(f"Direct match found: '{name}'")
            return self.name_to_full[name]
        
        # Full customer string
        if name in self.customers:
            logger.info(f"Full customer string provided: '{name}'")
            return name
        
        # Case-insensitive match
        name_lower = name.lower()
        for short_name, full_name in self.name_to_full.items():
            if short_name.lower() == name_lower:
                logger.info(f"Case-insensitive match found: '{name}' -> '{full_name}'")
                return full_name
        
        # Flexible matching
        logger.info(f"Attempting flexible matching for: '{name}'")
        flexible_result = self.flexible_match(name)
        if flexible_result:
            logger.info(f"Flexible match found: '{name}' -> '{flexible_result}'")
            return flexible_result
        
        # GPT fallback
        logger.info(f"Flexible matching failed for: '{name}'. Trying GPT mapping...")
        gpt_result = await self.map_customer_with_gpt(name)
        if gpt_result:
            logger.info(f"GPT successfully mapped: '{name}' -> '{gpt_result}'")
            return gpt_result
        
        logger.warning(f"Could not find customer: '{name}'")
        return None

    def flexible_match(self, input_name: str) -> Optional[str]:
        if not self.name_to_full:
            logger.debug("Flexible matching - No customers available")
            return None
        
        cleaned = re.sub(r'\s+', ' ', input_name.strip()).lower()
        logger.debug(f"Flexible matching - Cleaned input: '{cleaned}'")
        
        words = cleaned.split()
        logger.debug(f"Flexible matching - Input words: {words}")
        
        best_score = 0
        best_match = None
        
        for short_name, full_name in self.name_to_full.items():
            short_lower = short_name.lower()
            
            # Sequence matcher for overall similarity
            score = difflib.SequenceMatcher(None, cleaned, short_lower).ratio()
            
            # Bonus for word matches
            short_words = short_lower.split()
            word_matches = sum(1 for word in words if word in short_words)
            score += (word_matches / max(len(words), 1)) * 0.2  # Bonus up to 20%
            
            if score > best_score:
                best_score = score
                best_match = full_name
        
        logger.debug(f"Flexible matching - Best match: '{best_match or 'None'}' (score: {best_score})")
        
        if best_score > 0.75:  # Adjustable threshold
            return best_match
        
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def map_customer_with_gpt(self, customer_name: str) -> Optional[str]:
        if not self.customers:
            logger.debug("No customers available for GPT mapping")
            return None
        
        customer_names = list(self.name_to_full.keys())
        closest_matches = difflib.get_close_matches(customer_name, customer_names, n=20, cutoff=0.2)
        
        if closest_matches:
            relevant_customers = [self.name_to_full[name] for name in closest_matches]
        else:
            relevant_customers = self.customers[:30]
        
        system_prompt = (
            "You are a customer name mapping assistant. Map the input name to the EXACT customer from the list.\n"
            "Handle typos, abbreviations, variations, and numbers (e.g., '2015' as a year). Return ONLY the exact customer string from the list, or 'null' if no match.\n\n"
            f"CUSTOMERS:\n{json.dumps(relevant_customers, ensure_ascii=False)}"
        )
        user_prompt = f"Find customer: {customer_name}"
        
        logger.debug(f"Calling GPT for customer: '{customer_name}'")
        logger.debug(f"GPT system prompt: {system_prompt}")
        logger.debug(f"GPT user prompt: {user_prompt}")
        
        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=100,
                temperature=0.1
            )
            
            result = response.choices[0].message.content.strip()
            logger.debug(f"GPT response: '{result}'")
            
            if result != "null" and result in self.customers:
                return result
            
            logger.debug(f"GPT returned invalid or 'null' result: '{result}'")
            return None
            
        except Exception as e:
            logger.error(f"GPT mapping error: {str(e)}\n{traceback.format_exc()}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def record_to_sheets(self, timestamp: str, customer: str, amount: str, source: str, sender: str) -> bool:
        try:
            # Prefer SHEET_ID if provided, else fall back to SHEET_NAME
            if SHEET_ID:
                logger.debug(f"Opening spreadsheet by ID: {SHEET_ID}")
                sheet = CLIENT.open_by_key(SHEET_ID)
            else:
                logger.debug(f"Opening spreadsheet by name: {SHEET_NAME}")
                sheet = CLIENT.open(SHEET_NAME)
            
            worksheet = sheet.worksheet(WORKSHEET_NAME)
            row = [timestamp, customer, amount, source, sender]
            response = worksheet.append_row(row)
            logger.debug(f"Sheets append response: {response}")
            logger.info(f"Recorded to Sheets: {row}")
            return True
        except gspread.exceptions.SpreadsheetNotFound as e:
            logger.error(f"Spreadsheet not found: {SHEET_NAME} (ID: {SHEET_ID or 'None'})\nResponse: {getattr(e, 'response', 'No response')}\n{traceback.format_exc()}")
            return False
        except gspread.exceptions.WorksheetNotFound as e:
            logger.error(f"Worksheet not found: {WORKSHEET_NAME} in spreadsheet {SHEET_NAME} (ID: {SHEET_ID or 'None'})\nResponse: {getattr(e, 'response', 'No response')}\n{traceback.format_exc()}")
            return False
        except gspread.exceptions.APIError as e:
            logger.error(f"Google Sheets API error: {str(e)}\nResponse: {e.response.text}\n{traceback.format_exc()}")
            return False
        except Exception as e:
            logger.error(f"Error recording to Sheets: {str(e)}\n{traceback.format_exc()}")
            return False

async def main() -> None:
    bot = PaymentBot()
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await bot.handle_message(update, context)

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Starting Payment Bot polling...")
    await application.run_polling(timeout=10)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {str(e)}")