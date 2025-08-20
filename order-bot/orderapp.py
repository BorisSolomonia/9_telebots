import json
import os
import logging
import asyncio
from typing import Optional, Dict, Any, List, Tuple
import openai
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import telegram.error
import time
import difflib
import nest_asyncio
import traceback
from httpx import Client

nest_asyncio.apply()

# Initialize logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Config from env vars
TELEGRAM_TOKEN = os.environ.get("ORDER_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SHEETS_CREDS = os.environ.get("SHEETS_CREDS", "credentials.json")
CUSTOMERS_JSON = os.environ.get("CUSTOMERS_JSON")
SHEET_NAME = os.environ.get("SHEET_NAME", "9_ტონა_ფული")
SHEET_ID = os.environ.get("SHEET_ID")
WORKSHEET_NAME = os.environ.get("WORKSHEET_NAME", "orders")
MESSAGE_COOLDOWN = 5
PENDING_ORDER_TIMEOUT = 300
CLEANUP_INTERVAL = 600
MAX_RETRIES = 3
RETRY_DELAY = 2

# Validate required env vars
if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    logger.error("Missing required environment variables: ORDER_BOT_TOKEN and/or OPENAI_API_KEY")
    raise ValueError("ORDER_BOT_TOKEN and OPENAI_API_KEY must be set")

try:
    openai_client = openai.OpenAI(
        api_key=OPENAI_API_KEY,
        http_client=Client(follow_redirects=True)
    )
    logger.info("OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {str(e)}\n{traceback.format_exc()}")
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

class OrderBot:
    def __init__(self) -> None:
        self.customers: List[str] = []
        self.name_to_full: Dict[str, str] = {}
        self.pending_messages: set[int] = set()
        self.admins = ["Boris Solomonia", "Giorgi შავერდაშვილი", "Shota Gabilaia"]
        self._load_customers()

    def _load_customers(self) -> None:
        self.customers = []
        if CUSTOMERS_JSON:
            try:
                self.customers = json.loads(CUSTOMERS_JSON)
                if not isinstance(self.customers, list):
                    raise ValueError("customers must contain a list of customer names")
                if not self.customers:
                    raise ValueError("customers is empty")
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

        self._build_customer_mapping()
        logger.info(f"Loaded {len(self.customers)} customers")

    def _build_customer_mapping(self) -> None:
        self.name_to_full.clear()
        for customer in self.customers:
            customer = customer.strip()
            if customer:
                match = re.match(r'\((.*?)\)\s*(.*)', customer)
                name = match.group(2).strip() if match else customer
                if name:
                    self.name_to_full[name] = customer

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

    async def save_customers(self) -> None:
        logger.warning("Customer updates not supported on Render; update CUSTOMERS_JSON environment variable manually")

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(telegram.error.NetworkError))
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message or update.edited_message
        if not message or not message.text:
            return

        text = message.text
        message_id = message.message_id
        username = message.from_user.username or f"{message.from_user.first_name} {message.from_user.last_name}".strip()
        is_edited = update.edited_message is not None
        source = 'Edited' if is_edited else 'Direct'

        user_id = update.effective_user.id
        if not self._check_rate_limit(context, user_id):
            await message.reply_text("გთხოვთ დაელოდოთ რამდენიმე წამს შემდეგი შეკვეთის გაგზავნამდე.")
            return

        if username in self.admins and text.lower().startswith("new "):
            new_customer = text[4:].strip()  # Remove "new " prefix
            self.add_customer(new_customer)
            await message.reply_text(f"✅ კლიენტი დამატებულია: {new_customer}")
            return

        if username in self.admins and context.user_data.get('adding_customer', False):
            await self._handle_add_customer(update, context, text, username)
            return

        if username in self.admins and message.reply_to_message:
            reply_msg = message.reply_to_message
            if reply_msg.from_user.is_bot and "ვერ მოიძებნა" in reply_msg.text:
                new_customer = text.strip()
                self.add_customer(new_customer)
                await message.reply_text(f"✅ კლიენტი დამატებულია: {new_customer}")
                return

        if await self._is_potential_order(text):
            await self._process_order(update, context, text, source, username, is_edited, message_id)
        else:
            await self._send_format_help(update.message or update.edited_message)

    def _check_rate_limit(self, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
        last_message_time = context.user_data.get(f'last_message_{user_id}', 0)
        if time.time() - last_message_time < MESSAGE_COOLDOWN:
            return False
        context.user_data[f'last_message_{user_id}'] = time.time()
        return True
    
    async def _is_potential_order(self, text: str) -> bool:
        pattern = r'^(.*?)\s+(\d+)\s*(GEL|kg|ლარი|კგ)?\s+(.+)$'
        return bool(re.search(pattern, text))
    
    async def _process_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                           text: str, source: str, username: str, 
                           is_edited: bool, message_id: int) -> None:
        customer_found = self._find_customer_in_text(text)
        
        if customer_found:
            logger.info(f"Customer '{customer_found}' found directly in text")
            parsed = self._parse_order_simple(text, customer_found)
            if parsed:
                if is_edited and message_id in self.pending_messages:
                    self.pending_messages.remove(message_id)
                await self.try_record(update, context, parsed['customer'], parsed['amount'], parsed['product'], source, username)
                return
        
        logger.info(f"Customer not found directly, using GPT to parse: {text}")
        parsed = await self.parse_order_with_gpt(text)
        if parsed and self._validate_parsed_order(parsed):
            name, amount, product = parsed['customer'], parsed['amount'], parsed['product']
            if is_edited and message_id in self.pending_messages:
                self.pending_messages.remove(message_id)
            await self.try_record(update, context, name, amount, product, source, username)
        else:
            logger.debug(f"Failed to parse order from: {text}")
            await self._send_format_help(update.message or update.edited_message)
    
    def _find_customer_in_text(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        for customer_name, full_name in self.name_to_full.items():
            if customer_name.lower() in text_lower:
                logger.debug(f"Found customer '{customer_name}' in text")
                return full_name
        words = text.split()
        for word in words[:3]:
            matches = difflib.get_close_matches(word, list(self.name_to_full.keys()), n=1, cutoff=0.8)
            if matches:
                customer_full = self.name_to_full[matches[0]]
                logger.debug(f"Found fuzzy match: '{word}' -> '{matches[0]}'")
                return customer_full
        return None
    
    def _parse_order_simple(self, text: str, customer_full: str) -> Optional[Dict[str, Any]]:
        customer_name = None
        for name, full in self.name_to_full.items():
            if full == customer_full:
                customer_name = name
                break
        
        if not customer_name:
            return None
        
        text_without_customer = text.replace(customer_name, '').strip()
        pattern = r'(\d+)\s*(GEL|kg|ლარი|კგ)?\s*(.+)'
        match = re.search(pattern, text_without_customer, re.IGNORECASE)
        
        if match:
            amount = int(match.group(1))
            product = match.group(3).strip()
            if amount > 0 and product:
                logger.info(f"Simple parse successful: {customer_full}, {amount}, {product}")
                return {
                    'customer': customer_full,
                    'amount': amount,
                    'product': product
                }
        logger.debug(f"Simple parse failed for: {text_without_customer}")
        return None
    
    def _validate_parsed_order(self, parsed: Dict[str, Any]) -> bool:
        if not isinstance(parsed, dict) or not all(key in parsed for key in ['customer', 'amount', 'product']):
            return False
        amount = parsed.get('amount', 0)
        product = parsed.get('product', '').strip()
        if amount <= 0 or not product:
            logger.debug(f"Invalid parsed data: amount={amount}, product='{product}'")
            return False
        return True
    
    async def _send_format_help(self, message) -> None:
        await message.reply_text(
            "ვერ მოხერხდა შეკვეთის ამოცნობა. გთხოვთ, გამოიყენოთ ფორმატი:\n"
            "1. 'შპს მაგსი 20 საქონლის ბარკალი'\n"
            "2. 'შპს მაგსი 20 GEL ხაჭაპური'\n"
            "3. 'ბაჩუკი უშხვანი 10 კგ ხორცი'\n\n"
            "თუ კლიენტი არ არსებობს, ადმინებმა გამოიყენონ 'new <სრული სახელი>'."
        )

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(multiplier=1, min=4, max=10), retry=retry_if_exception_type(openai.RateLimitError))
    async def parse_order_with_gpt(self, text: str) -> Optional[Dict[str, Any]]:
        customer_list_all_short = list(self.name_to_full.keys())
        first_words = text.split()[:3]
        closest_matches = set()
        
        for word in first_words:
            matches = difflib.get_close_matches(word, customer_list_all_short, n=20, cutoff=0.4)
            closest_matches.update(matches)
        
        if closest_matches:
            customer_list = [self.name_to_full[short_name] for short_name in closest_matches]
        else:
            customer_list = list(self.name_to_full.values())[:50]
        
        system_prompt = (
            "You are an order processing assistant for a meat distribution business in Georgia. "
            "Extract order information from customer messages and map customer names to the exact names from the provided list.\n\n"
            f"AVAILABLE CUSTOMERS:\n{json.dumps(customer_list, ensure_ascii=False, indent=2)}\n\n"
            "INSTRUCTIONS:\n"
            "1. Extract customer name, amount (positive integer), and product from the message.\n"
            "2. Map the customer name to the EXACT name from the list, handling typos, abbreviations, partial names (e.g., 'ვარკეთილი' for 'ვარკეთილი მენეჯმენტი'), and numbers (e.g., '2015' as a year).\n"
            "3. Remove units like GEL, kg, ლარი, კგ from amount.\n"
            "4. Product is the item being ordered (e.g., 'ხორცი', 'ფილე'). Exclude commercial terms (e.g., 'ad', 'promo', 'sale').\n"
            "5. Return valid JSON: {\"customer\": \"exact_name_from_list\", \"amount\": number, \"product\": \"item_name\"}.\n"
            "6. If you cannot extract all fields or find a matching customer, or if the message contains commercial content (e.g., 'ad', 'sale'), return: null\n\n"
            "Examples:\n"
            "Input: 'ვარკეთილი 20 ხორცი'\n"
            "Output: {\"customer\": \"(405361629-დღგ) შპს ვარკეთილი მენეჯმენტი\", \"amount\": 20, \"product\": \"ხორცი\"}\n"
            "Input: 'ბაჩუკი 15 კგ ფილე'\n"
            "Output: {\"customer\": \"(62004022906) ბაჩუკი უშხვანი\", \"amount\": 15, \"product\": \"ფილე\"}\n"
            "Input: 'ფასანაური 2015 10 საქონლის ბარკალი'\n"
            "Output: {\"customer\": \"ფასანაური\", \"amount\": 10, \"product\": \"საქონლის ბარკალი\"}\n"
            "Input: 'ad for meat sale'\n"
            "Output: null"
        )
        
        user_prompt = f"Parse this order message: {text}"
        
        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=200,
                temperature=0.1
            )
            content = response.choices[0].message.content.strip()
            
            logger.debug(f"GPT system prompt: {system_prompt}")
            logger.debug(f"GPT user prompt: {user_prompt}")
            logger.debug(f"GPT response: '{content}'")

            if content.lower() == "null" or content == '"null"':
                logger.info("OpenAI returned null - could not parse order")
                return None

            content = content.replace("'", "\"").strip()
            if not content.startswith('{'):
                json_match = re.search(r'\{.*\}', content)
                if json_match:
                    content = json_match.group()
                else:
                    logger.warning(f"No JSON found in response: {content}")
                    return None
            
            parsed = json.loads(content)
            
            if self._validate_parsed_order(parsed):
                customer_name = parsed['customer']
                if customer_name not in self.name_to_full.values():
                    logger.warning(f"GPT returned customer '{customer_name}' not in our full customer list")
                    return None
                
                logger.info(f"OpenAI API Success - Parsed: customer='{parsed['customer']}', amount={parsed['amount']}, product='{parsed['product']}'")
                return parsed
            else:
                logger.warning(f"OpenAI API Validation Failed - Invalid parsed data: {parsed}")
                return None
                
        except openai.AuthenticationError as e:
            logger.error(f"OpenAI authentication error for text '{text}': {e}\n{traceback.format_exc()}")
            return None
        except openai.RateLimitError as e:
            logger.error(f"OpenAI rate limit error for text '{text}': {e}\n{traceback.format_exc()}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error for text '{text}': {e}, raw response: {content}\n{traceback.format_exc()}")
            return None
        except Exception as e:
            logger.error(f"OpenAI parse error for text '{text}': {e}, raw response: {content if 'content' in locals() else 'No response received'}\n{traceback.format_exc()}")
            return None

    async def _handle_add_customer(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, username: str) -> None:
        new_customer = text.strip()
        match = re.match(r'\((.*?)\)\s*(.*)', new_customer)
        new_name = match.group(2).strip() if match else new_customer
        full = new_customer

        pending = context.user_data.get('pending_order')
        if pending and new_name == pending['name']:
            if new_name in self.name_to_full:
                await update.message.reply_text("კლიენტი უკვე არსებობს.")
                return
            self.add_customer(full)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await self.record_to_sheets(timestamp, full, str(pending['amount']), pending['product'], username)
            await update.message.reply_text(f"ახალი კლიენტი დამატებულია და შეკვეთა ჩაწერილია: {full} {pending['amount']} {pending['product']}")
        else:
            await update.message.reply_text("სახელი არ ემთხვევა.")

        context.user_data['adding_customer'] = False
        context.user_data.pop('pending_order', None)

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(telegram.error.NetworkError))
    async def try_record(self, update: Update, context: ContextTypes.DEFAULT_TYPE, name: str, amount: float, product: str, source: str, username: str) -> None:
        message = update.message or update.edited_message
        customer_full = None
        if name in self.name_to_full.values():
            customer_full = name
            logger.debug(f"Using full customer name: {customer_full}")
        else:
            customer_full = self.name_to_full.get(name)
            logger.debug(f"Looked up short name '{name}' -> {customer_full}")
        
        if customer_full:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            try:
                await self.record_to_sheets(timestamp, customer_full, str(amount), product, username)
                await message.reply_text(f"ჩაწერილი შეკვეთა: {customer_full} {amount} {product}")
            except Exception:
                await message.reply_text("❌ ვერ მოხერხდა ჩაწერა Google Sheets-ში. გთხოვთ გადაამოწმოთ Spreadsheet ID ან Sheet-ის სახელი.")
        else:
            message_id = message.message_id
            self.pending_messages.add(message_id)
            await self._send_prompt(message, f"კლიენტი '{name}' ვერ მოიძებნა. გსურთ ახალი კლიენტის დამატება?", [
                [InlineKeyboardButton("დიახ", callback_data=f"add_yes_{message_id}"),
                 InlineKeyboardButton("არა", callback_data=f"add_no_{message_id}")]
            ])
            context.user_data['pending_order'] = {'name': name, 'amount': amount, 'product': product, 'source': source, 'message_id': message_id, 'timestamp': time.time()}

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def record_to_sheets(self, timestamp: str, customer: str, amount: str, product: str, sender: str) -> None:
        try:
            sanitized_row = self._sanitize_sheet_data([timestamp, customer, amount, product, sender])
            worksheet = await self.get_worksheet()
            response = worksheet.append_row(sanitized_row)
            logger.debug(f"Sheets append response: {response}")
            logger.info(f"Recorded to Sheets: {sanitized_row}")
        except gspread.exceptions.SpreadsheetNotFound as e:
            logger.error(f"Spreadsheet not found: {SHEET_NAME} (ID: {SHEET_ID or 'None'})\nResponse: {getattr(e, 'response', 'No response')}\n{traceback.format_exc()}")
            raise
        except gspread.exceptions.WorksheetNotFound as e:
            logger.error(f"Worksheet not found: {WORKSHEET_NAME} in spreadsheet {SHEET_NAME} (ID: {SHEET_ID or 'None'})\nResponse: {getattr(e, 'response', 'No response')}\n{traceback.format_exc()}")
            raise
        except gspread.exceptions.APIError as e:
            logger.error(f"Google Sheets API error: {str(e)}\nResponse: {e.response.text}\n{traceback.format_exc()}")
            raise
        except Exception as e:
            logger.error(f"Error recording to Sheets: {str(e)}\n{traceback.format_exc()}")
            raise

    async def get_worksheet(self):
        try:
            if SHEET_ID:
                logger.debug(f"Opening spreadsheet by ID: {SHEET_ID}")
                sheet = CLIENT.open_by_key(SHEET_ID)
            else:
                logger.debug(f"Opening spreadsheet by name: {SHEET_NAME}")
                sheet = CLIENT.open(SHEET_NAME)
            
            try:
                worksheet = sheet.worksheet(WORKSHEET_NAME)
            except gspread.exceptions.WorksheetNotFound:
                logger.info(f"Creating new worksheet: {WORKSHEET_NAME}")
                worksheet = sheet.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=5)
            
            return worksheet
        except gspread.exceptions.SpreadsheetNotFound:
            logger.info(f"Creating new spreadsheet: {SHEET_NAME}")
            sheet = CLIENT.create(SHEET_NAME)
            worksheet = sheet.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=5)
            return worksheet

    def _sanitize_sheet_data(self, row: List[str]) -> List[str]:
        return [str(item).replace('\n', ' ').replace('\r', ' ') for item in row]

    @retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(telegram.error.NetworkError))
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        data = query.data
        parts = data.split('_')
        action = parts[0]
        sub_action = parts[1] if len(parts) > 1 else ''
        message_id = int(parts[-1])

        if action == "add" and sub_action == "yes":
            await query.edit_message_text("გთხოვთ დაწეროთ ახალი კლიენტის სახელი")
            context.user_data['adding_customer'] = True
        elif action == "add" and sub_action == "no":
            await query.edit_message_text("იგნორირებულია.")
            context.user_data.pop('pending_order', None)

    async def _send_prompt(self, message, text: str, keyboard: list) -> None:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text(text, reply_markup=reply_markup)

async def main() -> None:
    bot = OrderBot()
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await bot.handle_message(update, context)

    async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await bot.handle_callback(update, context)

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_handler))
    application.add_handler(CallbackQueryHandler(cb_handler))

    if application.job_queue:
        async def clear_pending(_) -> None:
            now = time.time()
            timeout = PENDING_ORDER_TIMEOUT
            for user_data in application.user_data.values():
                if 'pending_order' in user_data and now - user_data['pending_order'].get('timestamp', 0) > timeout:
                    user_data.pop('pending_order', None)
            bot.pending_messages.clear()
            logger.debug("Cleared expired pending orders")
        
        application.job_queue.run_repeating(clear_pending, interval=CLEANUP_INTERVAL, first=CLEANUP_INTERVAL)

    logger.info("Starting Order Bot polling...")
    await application.run_polling(timeout=10)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}\n{traceback.format_exc()}")