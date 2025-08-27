import logging
import asyncio
import json
from typing import Optional, Dict, Any, List, Tuple
import os
import openai
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_fixed, wait_exponential, retry_if_exception_type
import nest_asyncio
import telegram.error
import time
import difflib
import aiofiles
from contextlib import asynccontextmanager

nest_asyncio.apply()

# Configuration class for better organization
class Config:
    TELEGRAM_TOKEN = os.environ['ORDER_BOT_TOKEN']
    OPENAI_API_KEY = os.environ['OPENAI_API_KEY']
    SHEET_NAME = os.environ.get('SHEET_NAME', '9_ტონა_ფული')
    WORKSHEET_NAME = os.environ.get('WORKSHEET_NAME', 'Payments')
    CREDS_FILE = os.environ['CREDS_FILE']
    CUSTOMERS_FILE = os.getenv('CUSTOMERS_FILE', 'customers.json')
    
    # Rate limiting
    MESSAGE_COOLDOWN = int(os.getenv('MESSAGE_COOLDOWN', '5'))
    PENDING_ORDER_TIMEOUT = int(os.getenv('PENDING_ORDER_TIMEOUT', '300'))
    CLEANUP_INTERVAL = int(os.getenv('CLEANUP_INTERVAL', '600'))
    
    # Retry configuration
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
    RETRY_DELAY = int(os.getenv('RETRY_DELAY', '2'))
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        if not cls.TELEGRAM_TOKEN or not cls.OPENAI_API_KEY:
            raise ValueError("ORDER_BOT_TOKEN and OPENAI_API_KEY must be set in environment variables")
        
        if not os.path.exists(cls.CREDS_FILE):
            raise ValueError(f"Credentials file not found: {cls.CREDS_FILE}")

Config.validate()

# Initialize OpenAI client
class OpenAIClient:
    def __init__(self):
        self.client = openai.OpenAI(api_key=Config.OPENAI_API_KEY)
        self._validate_api_key()
    
    def _validate_api_key(self) -> None:
        """Validate OpenAI API key."""
        try:
            self.client.models.list()
        except openai.AuthenticationError:
            raise ValueError("Invalid OPENAI_API_KEY")
        except Exception as e:
            raise ValueError(f"Failed to validate OPENAI_API_KEY: {e}")

# Google Sheets client with connection management
class SheetsClient:
    def __init__(self):
        self.scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        self._client = None
        self._sheet = None
        self._worksheet = None
    
    @asynccontextmanager
    async def get_client(self):
        """Get sheets client with proper resource management."""
        if not self._client:
            creds = ServiceAccountCredentials.from_json_keyfile_name(Config.CREDS_FILE, self.scope)
            self._client = gspread.authorize(creds)
        yield self._client
    
    async def get_worksheet(self):
        """Get or create worksheet."""
        async with self.get_client() as client:
            try:
                sheet = client.open(Config.SHEET_NAME)
            except gspread.exceptions.SpreadsheetNotFound:
                sheet = client.create(Config.SHEET_NAME)
                logger.info(f"Created new spreadsheet: {Config.SHEET_NAME}")
            
            try:
                worksheet = sheet.worksheet(Config.WORKSHEET_NAME)
            except gspread.exceptions.WorksheetNotFound:
                worksheet = sheet.add_worksheet(title=Config.WORKSHEET_NAME, rows=1000, cols=5)
                logger.info(f"Created new worksheet: {Config.WORKSHEET_NAME}")
            
            return worksheet

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

class OrderBot:
    """Class encapsulating the order bot logic and state."""

    def __init__(self) -> None:
        self.customers: List[str] = []
        self.name_to_full: Dict[str, str] = {}
        self.pending_messages: set[int] = set()
        self.openai_client = OpenAIClient()
        self.sheets_client = SheetsClient()
        asyncio.create_task(self._load_customers())

    async def _load_customers(self) -> None:
        """Load customers from customers.json asynchronously."""
        try:
            async with aiofiles.open(Config.CUSTOMERS_FILE, 'r', encoding='utf-8') as f:
                content = await f.read()
                self.customers = json.loads(content)
            
            if not isinstance(self.customers, list):
                raise ValueError(f"{Config.CUSTOMERS_FILE} must contain a list of customer names")
            if not self.customers:
                raise ValueError(f"{Config.CUSTOMERS_FILE} is empty")
                
        except FileNotFoundError:
            raise ValueError(f"{Config.CUSTOMERS_FILE} file not found")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {Config.CUSTOMERS_FILE}: {e}")
        
        self._build_customer_mapping()
        logger.info(f"Loaded {len(self.customers)} customers from {Config.CUSTOMERS_FILE}")
    
    def _build_customer_mapping(self) -> None:
        """Build customer name to full name mapping."""
        self.name_to_full.clear()
        for customer in self.customers:
            customer = customer.strip()
            if customer:
                match = re.match(r'\((.*?)\)\s*(.*)', customer)
                name = match.group(2).strip() if match else customer
                if name:
                    self.name_to_full[name] = customer

    async def save_customers(self) -> None:
        """Save customers to customers.json asynchronously."""
        async with aiofiles.open(Config.CUSTOMERS_FILE, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(self.customers, ensure_ascii=False, indent=4))
        logger.info(f"Saved {Config.CUSTOMERS_FILE}")

    @retry(stop=stop_after_attempt(Config.MAX_RETRIES), wait=wait_fixed(Config.RETRY_DELAY), retry=retry_if_exception_type(telegram.error.NetworkError))
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming or edited messages."""
        message = update.message or update.edited_message
        if not message or not message.text:
            return

        text = message.text
        message_id = message.message_id
        username = message.from_user.username or f"{message.from_user.first_name} {message.from_user.last_name}".strip()
        is_edited = update.edited_message is not None
        source = 'Edited' if is_edited else 'Direct'

        # Message flood control
        user_id = update.effective_user.id
        if not self._check_rate_limit(context, user_id):
            await message.reply_text("გთხოვთ დაელოდოთ რამდენიმე წამს შემდეგი შეკვეთის გაგზავნამდე.")
            return

        # Adding mode (for new customers)
        if context.user_data.get('adding_customer', False):
            await self._handle_add_customer(update, context, text, username)
            return

        # Order parsing logic
        if await self._is_potential_order(text):
            await self._process_order(update, context, text, source, username, is_edited, message_id)
        else:
            await self._send_format_help(message)

    def _check_rate_limit(self, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
        """Check if user is within rate limit."""
        last_message_time = context.user_data.get(f'last_message_{user_id}', 0)
        if time.time() - last_message_time < Config.MESSAGE_COOLDOWN:
            return False
        context.user_data[f'last_message_{user_id}'] = time.time()
        return True
    
    async def _is_potential_order(self, text: str) -> bool:
        """Check if text looks like an order."""
        pattern = r'^(.*?)\s+(\d+)\s*(GEL|kg)?\s+(.+)$'
        return bool(re.search(pattern, text))
    
    async def _process_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                           text: str, source: str, username: str, 
                           is_edited: bool, message_id: int) -> None:
        """Process potential order message with proper customer mapping flow."""
        # First try to find customer directly in the text
        customer_found = self._find_customer_in_text(text)
        
        if customer_found:
            # Customer found directly, try to parse amount and product from remaining text
            logger.info(f"Customer '{customer_found}' found directly in text")
            parsed = self._parse_order_simple(text, customer_found)
            if parsed:
                if is_edited and message_id in self.pending_messages:
                    self.pending_messages.remove(message_id)
                await self.try_record(update, context, parsed['customer'], parsed['amount'], parsed['product'], source, username)
                return
        
        # Customer not found directly, use GPT to parse and map customer
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
        """Try to find a known customer name directly in the text."""
        text_lower = text.lower()
        
        # Look for exact matches first, then partial matches
        for customer_name, full_name in self.name_to_full.items():
            if customer_name.lower() in text_lower:
                logger.debug(f"Found customer '{customer_name}' in text")
                return full_name
        
        # Try fuzzy matching for typos
        words = text.split()
        for word in words[:3]:  # Check first 3 words for customer names
            matches = difflib.get_close_matches(word, list(self.name_to_full.keys()), n=1, cutoff=0.8)
            if matches:
                customer_full = self.name_to_full[matches[0]]
                logger.debug(f"Found fuzzy match: '{word}' -> '{matches[0]}'")
                return customer_full
        
        return None
    
    def _parse_order_simple(self, text: str, customer_full: str) -> Optional[Dict[str, Any]]:
        """Parse order when customer is already known."""
        # Remove customer name from text to get amount and product
        customer_name = None
        for name, full in self.name_to_full.items():
            if full == customer_full:
                customer_name = name
                break
        
        if not customer_name:
            return None
        
        # Remove customer name from text
        text_without_customer = text.replace(customer_name, '').strip()
        
        # Extract amount and product using regex
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
        """Validate parsed order data."""
        if not isinstance(parsed, dict) or not all(key in parsed for key in ['customer', 'amount', 'product']):
            return False
        
        amount = parsed.get('amount', 0)
        product = parsed.get('product', '').strip()
        
        if amount <= 0 or not product:
            logger.debug(f"Invalid parsed data: amount={amount}, product='{product}'")
            return False
        
        return True
    
    async def _send_format_help(self, message) -> None:
        """Send format help message."""
        await message.reply_text(
            "ვერ მოხერხდა შეკვეთის ამოცნობა. გთხოვთ, გამოიყენოთ ფორმატი:\n"
            "1. 'შპს მაგსი 20 საქონლის ბარკალი'\n"
            "2. 'შპს მაგსი 20 GEL ხაჭაპური'\n"
            "3. 'ბაჩუკი უშხვანი 10 კგ ხორცი'"
        )

    @retry(stop=stop_after_attempt(Config.MAX_RETRIES), wait=wait_exponential(multiplier=1, min=4, max=10), retry=retry_if_exception_type(openai.RateLimitError))
    async def parse_order_with_gpt(self, text: str) -> Optional[Dict[str, Any]]:
        """Use OpenAI to parse order from message with system prompt containing customer list."""
        # Get a manageable list of FULL customer names for the system prompt
        customer_list_all_short = list(self.name_to_full.keys())
        
        # Use difflib to find closest matches to reduce the list size for GPT
        first_words = text.split()[:3]  # First 3 words might contain customer name
        closest_matches = set()
        
        for word in first_words:
            matches = difflib.get_close_matches(word, customer_list_all_short, n=20, cutoff=0.4)
            closest_matches.update(matches)
        
        # Convert to full names and limit the list
        if closest_matches:
            customer_list = [self.name_to_full[short_name] for short_name in closest_matches]
        else:
            # Use first 50 full customer names
            customer_list = list(self.name_to_full.values())[:50]
        
        # Create system prompt with customer names
        system_prompt = (
            "You are an order processing assistant for a meat distribution Business based in Georgia. "
            "Your task is to extract order information from customer messages and map customer names to the exact names from the provided list.\n\n"
            f"AVAILABLE CUSTOMERS:\n{json.dumps(customer_list, ensure_ascii=False, indent=2)}\n\n"
            "INSTRUCTIONS:\n"
            "1. Extract customer name, amount (number), and product from the message\n"
            "2. Map the customer name to the EXACT name from the list above (handle typos and variations)\n"
            "3. Amount should be a positive integer (remove units like GEL, kg, ლარი, კგ)\n"
            "4. Product should be the item being ordered\n"
            "5. Return ONLY valid JSON: {\"customer\": \"exact_name_from_list of AVAILABLE CUSTOMERS\", \"amount\": number, \"product\": \"item_name\"}\n"
            "6. If you cannot extract all three fields clearly, return: null\n\n"
            "Examples:\n"
            "Input: 'შპს მაგსი 20 საქონლის ბარკალი'\n"
            "Output: {\"customer\": \"(405135946-დღგ) შპს მაგსი\", \"amount\": 20, \"product\": \"საქონლის ბარკალი\"}\n\n"
            "Input: 'ბაჩუკი 15  ხორცი'\n"
            "Output: {\"customer\": \"(62004022906) ბაჩუკი უშხვანი\", \"amount\": 15, \"product\": \"ხორცი\"}"
            "Input: 'წსქვლი 15  ფილე'\n"
            "Output: {\"customer\": \"(202200778-დღგ) შპს წისქვილი ჯგუფი\", \"amount\": 15, \"product\": \"ფილე\"}"
            
        )
        
        user_prompt = f"Parse this order message: {text}"
        
        try:
            response = self.openai_client.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=200,
                temperature=0.1  # Low temperature for consistent parsing
            )
            content = response.choices[0].message.content.strip()
            
            # Log the full interaction for debugging
            logger.info(f"OpenAI API Request - Input text: '{text}'")
            logger.info(f"OpenAI API Request - Customer list size: {len(customer_list)}")
            logger.info(f"OpenAI API Response - Raw output: {content}")
            logger.info(f"OpenAI API Usage - Tokens used: {response.usage.total_tokens if response.usage else 'Unknown'}")

            if content.lower() == "null" or content == '\"null\"':
                logger.info("OpenAI returned null - could not parse order")
                return None

            # Clean and parse JSON
            content = content.replace("'", "\"").strip()
            if not content.startswith('{'):
                # Sometimes GPT adds extra text, extract JSON
                import re
                json_match = re.search(r'\{.*\}', content)
                if json_match:
                    content = json_match.group()
                else:
                    logger.warning(f"No JSON found in response: {content}")
                    return None
            
            parsed = json.loads(content)
            
            if self._validate_parsed_order(parsed):
                # Verify customer exists in our list (should be full name since we send full names to GPT)
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
            logger.error(f"OpenAI authentication error for text '{text}': {e}")
            return None
        except openai.RateLimitError as e:
            logger.error(f"OpenAI rate limit error for text '{text}': {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error for text '{text}': {e}, raw response: {content}")
            return None
        except Exception as e:
            logger.error(f"OpenAI parse error for text '{text}': {e}, raw response: {content if 'content' in locals() else 'No response received'}")
            return None

    async def _handle_add_customer(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, username: str) -> None:
        """Handle adding new customer."""
        new_customer = text.strip()
        match = re.match(r'\((.*?)\)\s*(.*)', new_customer)
        new_name = match.group(2).strip() if match else new_customer
        full = new_customer

        pending = context.user_data.get('pending_order')
        if pending and new_name == pending['name']:
            if new_name in self.name_to_full:
                await update.message.reply_text("კლიენტი უკვე არსებობს.")
                return
            self.customers.append(full)
            self.name_to_full[new_name] = full
            await self.save_customers()
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await self.record_to_sheets(timestamp, full, str(pending['amount']), pending['product'], username)
            await update.message.reply_text(f"ახალი კლიენტი დამატებულია და შეკვეთა ჩაწერილია: {full} {pending['amount']} {pending['product']}")
        else:
            await update.message.reply_text("სახელი არ ემთხვევა.")

        context.user_data['adding_customer'] = False
        context.user_data.pop('pending_order', None)

    @retry(stop=stop_after_attempt(Config.MAX_RETRIES), wait=wait_fixed(Config.RETRY_DELAY), retry=retry_if_exception_type(telegram.error.NetworkError))
    async def try_record(self, update: Update, context: ContextTypes.DEFAULT_TYPE, name: str, amount: float, product: str, source: str, username: str) -> None:
        """Try to record order after validation."""
        message = update.message or update.edited_message
        
        # Check if name is already a full customer name (from GPT)
        customer_full = None
        if name in self.name_to_full.values():
            # Name is already a full customer name
            customer_full = name
            logger.debug(f"Using full customer name: {customer_full}")
        else:
            # Name might be a short name, look it up
            customer_full = self.name_to_full.get(name)
            logger.debug(f"Looked up short name '{name}' -> {customer_full}")
        
        if customer_full:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await self.record_to_sheets(timestamp, customer_full, str(amount), product, username)
            await message.reply_text(f"ჩაწერილი შეკვეთა: {customer_full} {amount} {product}")
        else:
            message_id = message.message_id
            self.pending_messages.add(message_id)
            await self._send_prompt(message, f"კლიენტი '{name}' არ მოიძებნა. გსურთ ახალი კლიენტის დამატება?", [
                [InlineKeyboardButton("დიახ", callback_data=f"add_yes_{message_id}"),
                 InlineKeyboardButton("არა", callback_data=f"add_no_{message_id}")]
            ])
            context.user_data['pending_order'] = {'name': name, 'amount': amount, 'product': product, 'source': source, 'message_id': message_id, 'timestamp': time.time()}

    @retry(stop=stop_after_attempt(Config.MAX_RETRIES), wait=wait_fixed(Config.RETRY_DELAY), retry=retry_if_exception_type(gspread.exceptions.APIError))
    async def record_to_sheets(self, timestamp: str, customer: str, amount: str, product: str, sender: str) -> None:
        """Record order to Google Sheets with improved error handling."""
        try:
            # Sanitize input data
            sanitized_row = self._sanitize_sheet_data([timestamp, customer, amount, product, sender])
            
            worksheet = await self.sheets_client.get_worksheet()
            worksheet.append_row(sanitized_row)
            logger.debug(f"Recorded to Sheets: {sanitized_row}")
            
        except gspread.exceptions.APIError as e:
            logger.error(f"Sheets API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Sheets error: {e}")
            raise
    
    def _sanitize_sheet_data(self, row: List[str]) -> List[str]:
        """Sanitize data before writing to sheets."""
        return [str(item).replace('\n', ' ').replace('\r', ' ') for item in row]

    @retry(stop=stop_after_attempt(Config.MAX_RETRIES), wait=wait_fixed(Config.RETRY_DELAY), retry=retry_if_exception_type(telegram.error.NetworkError))
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle button callbacks."""
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
        """Helper to send prompt."""
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text(text, reply_markup=reply_markup)

@retry(stop=stop_after_attempt(5), wait=wait_fixed(5), retry=retry_if_exception_type((telegram.error.NetworkError, telegram.error.TimedOut)))
async def start_polling(application: Application) -> None:
    """Start polling with retry on network errors."""
    try:
        await application.run_polling(timeout=10.0)
    except telegram.error.NetworkError as e:
        logger.error(f"Network error during polling: {e}")
        raise
    except telegram.error.TimedOut as e:
        logger.error(f"Timeout during polling: {e}")
        raise

async def main() -> None:
    """Main bot setup and run."""
    bot = OrderBot()
    application = Application.builder().token(Config.TELEGRAM_TOKEN).build()
    await application.initialize()

    async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await bot.handle_message(update, context)
    
    async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await bot.handle_callback(update, context)
    
    application.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) & (filters.ChatType.PRIVATE | filters.ChatType.GROUP | filters.ChatType.SUPERGROUP), msg_handler))
    application.add_handler(CallbackQueryHandler(cb_handler))

    if application.job_queue:
        async def clear_pending(_) -> None:
            now = time.time()
            timeout = Config.PENDING_ORDER_TIMEOUT
            for user_data in application.user_data.values():
                if 'pending_order' in user_data and now - user_data['pending_order'].get('timestamp', 0) > timeout:
                    user_data.pop('pending_order', None)
            bot.pending_messages.clear()
            logger.debug("Cleared expired pending orders")
        
        application.job_queue.run_repeating(clear_pending, interval=Config.CLEANUP_INTERVAL, first=Config.CLEANUP_INTERVAL)

    try:
        await start_polling(application)
    except telegram.error.Conflict as e:
        logger.error(f"Bot conflict - another instance is running: {e}")
        logger.info("Please stop other bot instances and try again")
        raise
    except telegram.error.NetworkError as e:
        logger.error(f"Failed to start polling after retries: {e}")
        raise
    except telegram.error.TimedOut as e:
        logger.error(f"Timeout error during initialization: {e}")
        raise
    finally:
        await application.shutdown()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}")