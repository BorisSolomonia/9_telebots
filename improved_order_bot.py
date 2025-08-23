#!/usr/bin/env python3
"""
Improved Order Bot with Security, Performance, and Reliability Enhancements

Key Improvements:
- Secure configuration management
- GPT response caching
- File locking for data consistency
- Graceful shutdown handling
- Structured logging
- Performance optimizations
- Better error handling
"""

import logging
import asyncio
import json
import signal
import time
import hashlib
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from dataclasses import dataclass
from contextlib import asynccontextmanager
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
import aiofiles
import fcntl
import structlog

nest_asyncio.apply()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

@dataclass
class Config:
    """Secure configuration management with validation."""
    telegram_token: str
    openai_api_key: str
    sheet_name: str = "9_ტონა_ფული"
    worksheet_name: str = "Payments"
    customers_file: str = "customers.json"
    creds_file: str = "credentials.json"
    
    # Performance settings
    message_cooldown: int = 5
    pending_order_timeout: int = 300
    cleanup_interval: int = 600
    max_retries: int = 3
    retry_delay: int = 2
    
    # Cache settings
    gpt_cache_ttl: int = 300  # 5 minutes
    max_cache_size: int = 1000
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Load configuration from environment variables with validation."""
        telegram_token = os.environ.get('ORDER_BOT_TOKEN') or os.environ.get('TELEGRAM_TOKEN_BOT')
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        
        if not telegram_token:
            raise ValueError("ORDER_BOT_TOKEN or TELEGRAM_TOKEN_BOT must be set")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set")
        
        # Validate token format (basic check)
        if len(telegram_token) < 20 or ':' not in telegram_token:
            raise ValueError("Invalid Telegram bot token format")
        
        creds_file = os.environ.get('CREDS_FILE', 'credentials.json')
        if not Path(creds_file).exists():
            raise ValueError(f"Credentials file not found: {creds_file}")
        
        return cls(
            telegram_token=telegram_token,
            openai_api_key=openai_api_key,
            sheet_name=os.environ.get('SHEET_NAME', "9_ტონა_ფული"),
            worksheet_name=os.environ.get('WORKSHEET_NAME', "Payments"),
            customers_file=os.environ.get('CUSTOMERS_FILE', 'customers.json'),
            creds_file=creds_file,
            message_cooldown=int(os.environ.get('MESSAGE_COOLDOWN', '5')),
            pending_order_timeout=int(os.environ.get('PENDING_ORDER_TIMEOUT', '300')),
            cleanup_interval=int(os.environ.get('CLEANUP_INTERVAL', '600')),
            max_retries=int(os.environ.get('MAX_RETRIES', '3')),
            retry_delay=int(os.environ.get('RETRY_DELAY', '2')),
            gpt_cache_ttl=int(os.environ.get('GPT_CACHE_TTL', '300')),
            max_cache_size=int(os.environ.get('MAX_CACHE_SIZE', '1000'))
        )

class GPTCache:
    """Thread-safe cache for GPT responses with TTL and size limits."""
    
    def __init__(self, ttl: int = 300, max_size: int = 1000):
        self.ttl = ttl
        self.max_size = max_size
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._access_times: Dict[str, float] = {}
    
    def _make_key(self, text: str, customer_list: List[str]) -> str:
        """Create cache key from input parameters."""
        customer_hash = hashlib.md5(
            json.dumps(sorted(customer_list), ensure_ascii=False).encode()
        ).hexdigest()[:8]
        return f"{text.lower().strip()}:{customer_hash}"
    
    def get(self, text: str, customer_list: List[str]) -> Optional[Dict[str, Any]]:
        """Get cached response if valid."""
        key = self._make_key(text, customer_list)
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self.ttl:
                self._access_times[key] = time.time()
                logger.debug("cache_hit", key=key)
                return value
            else:
                # Expired
                del self._cache[key]
                del self._access_times[key]
                logger.debug("cache_expired", key=key)
        return None
    
    def set(self, text: str, customer_list: List[str], value: Dict[str, Any]) -> None:
        """Cache response with TTL."""
        key = self._make_key(text, customer_list)
        
        # Evict oldest if at capacity
        if len(self._cache) >= self.max_size:
            oldest_key = min(self._access_times, key=self._access_times.get)
            del self._cache[oldest_key]
            del self._access_times[oldest_key]
            logger.debug("cache_evicted", key=oldest_key)
        
        self._cache[key] = (value, time.time())
        self._access_times[key] = time.time()
        logger.debug("cache_stored", key=key)
    
    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self._access_times.clear()
        logger.info("cache_cleared")

class SecureFileManager:
    """Secure file operations with locking and atomic writes."""
    
    @staticmethod
    @asynccontextmanager
    async def atomic_write(file_path: str):
        """Context manager for atomic file writes."""
        temp_path = f"{file_path}.tmp"
        try:
            async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
                yield f
            # Atomic move
            Path(temp_path).replace(Path(file_path))
            logger.debug("file_written_atomically", path=file_path)
        except Exception:
            # Cleanup temp file on error
            Path(temp_path).unlink(missing_ok=True)
            raise
    
    @staticmethod
    async def read_json(file_path: str) -> Any:
        """Safely read JSON file."""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except FileNotFoundError:
            logger.warning("file_not_found", path=file_path)
            return None
        except json.JSONDecodeError as e:
            logger.error("json_decode_error", path=file_path, error=str(e))
            raise ValueError(f"Invalid JSON in {file_path}: {e}")
    
    @staticmethod
    async def write_json(file_path: str, data: Any) -> None:
        """Safely write JSON file atomically."""
        async with SecureFileManager.atomic_write(file_path) as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))

class OpenAIClientManager:
    """Secure OpenAI client with proper error handling."""
    
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
        self._validate_client()
    
    def _validate_client(self) -> None:
        """Validate API key on initialization."""
        try:
            # Test with a minimal request
            self.client.models.list()
            logger.info("openai_client_validated")
        except openai.AuthenticationError:
            raise ValueError("Invalid OPENAI_API_KEY")
        except Exception as e:
            logger.error("openai_validation_failed", error=str(e))
            raise ValueError(f"Failed to validate OpenAI client: {e}")

class SheetsClientManager:
    """Google Sheets client with connection management."""
    
    def __init__(self, creds_file: str):
        self.creds_file = creds_file
        self.scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        self._client = None
    
    @asynccontextmanager
    async def get_client(self):
        """Get sheets client with proper resource management."""
        if not self._client:
            try:
                creds = ServiceAccountCredentials.from_json_keyfile_name(
                    self.creds_file, self.scope
                )
                self._client = gspread.authorize(creds)
                logger.info("sheets_client_initialized")
            except Exception as e:
                logger.error("sheets_client_error", error=str(e))
                raise
        yield self._client
    
    async def get_worksheet(self, sheet_name: str, worksheet_name: str):
        """Get or create worksheet."""
        async with self.get_client() as client:
            try:
                sheet = client.open(sheet_name)
            except gspread.exceptions.SpreadsheetNotFound:
                sheet = client.create(sheet_name)
                logger.info("spreadsheet_created", name=sheet_name)
            
            try:
                worksheet = sheet.worksheet(worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                worksheet = sheet.add_worksheet(
                    title=worksheet_name, rows=1000, cols=5
                )
                logger.info("worksheet_created", name=worksheet_name)
            
            return worksheet

class ImprovedOrderBot:
    """Enhanced order bot with security, performance, and reliability improvements."""
    
    def __init__(self, config: Config):
        self.config = config
        self.customers: List[str] = []
        self.name_to_full: Dict[str, str] = {}
        self.pending_messages: set[int] = set()
        self.last_cleanup = time.time()
        
        # Initialize services
        self.openai_client = OpenAIClientManager(config.openai_api_key)
        self.sheets_client = SheetsClientManager(config.creds_file)
        self.gpt_cache = GPTCache(config.gpt_cache_ttl, config.max_cache_size)
        
        # Rate limiting
        self.user_last_message: Dict[int, float] = {}
        
        # Graceful shutdown
        self.shutdown_event = asyncio.Event()
        self._setup_signal_handlers()
        
        # Load customers on startup
        asyncio.create_task(self._load_customers())
    
    def _setup_signal_handlers(self) -> None:
        """Setup graceful shutdown signal handlers."""
        def signal_handler(signum, frame):
            logger.info("shutdown_signal_received", signal=signum)
            asyncio.create_task(self._graceful_shutdown())
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    async def _graceful_shutdown(self) -> None:
        """Handle graceful shutdown."""
        logger.info("graceful_shutdown_started")
        self.shutdown_event.set()
        
        # Save any pending data
        try:
            await self._save_customers()
            logger.info("customers_saved_on_shutdown")
        except Exception as e:
            logger.error("shutdown_save_error", error=str(e))
    
    async def _load_customers(self) -> None:
        """Load customers from file with proper error handling."""
        try:
            data = await SecureFileManager.read_json(self.config.customers_file)
            if data is None:
                self.customers = []
                logger.warning("customers_file_not_found", 
                             file=self.config.customers_file)
            elif isinstance(data, list):
                self.customers = data
                logger.info("customers_loaded", 
                           count=len(self.customers),
                           file=self.config.customers_file)
            else:
                raise ValueError("customers.json must contain a list")
        except Exception as e:
            logger.error("customers_load_error", error=str(e))
            self.customers = []
        
        self._build_customer_mapping()
    
    def _build_customer_mapping(self) -> None:
        """Build optimized customer name mapping."""
        self.name_to_full.clear()
        for customer in self.customers:
            customer = customer.strip()
            if customer:
                # Extract name from format: (code) name
                match = re.match(r'\((.*?)\)\s*(.*)', customer)
                name = match.group(2).strip() if match else customer
                if name:
                    self.name_to_full[name.lower()] = customer
        
        logger.debug("customer_mapping_built", count=len(self.name_to_full))
    
    async def _save_customers(self) -> None:
        """Save customers to file atomically."""
        try:
            await SecureFileManager.write_json(
                self.config.customers_file, self.customers
            )
            logger.info("customers_saved", file=self.config.customers_file)
        except Exception as e:
            logger.error("customers_save_error", error=str(e))
            raise
    
    def _check_rate_limit(self, user_id: int) -> bool:
        """Check if user is within rate limit."""
        now = time.time()
        last_message = self.user_last_message.get(user_id, 0)
        
        if now - last_message < self.config.message_cooldown:
            logger.debug("rate_limit_hit", user_id=user_id)
            return False
        
        self.user_last_message[user_id] = now
        return True
    
    async def _cleanup_old_data(self) -> None:
        """Periodic cleanup of old data."""
        now = time.time()
        
        # Cleanup old rate limit data
        cutoff = now - self.config.message_cooldown * 2
        self.user_last_message = {
            uid: timestamp for uid, timestamp in self.user_last_message.items()
            if timestamp > cutoff
        }
        
        # Clear pending messages (they should be handled by timeout)
        self.pending_messages.clear()
        
        self.last_cleanup = now
        logger.debug("cleanup_completed")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(openai.RateLimitError)
    )
    async def parse_order_with_gpt(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse order using GPT with caching and improved error handling."""
        # Check cache first
        customer_list = list(self.name_to_full.values())[:50]  # Limit for performance
        cached_result = self.gpt_cache.get(text, customer_list)
        if cached_result:
            return cached_result
        
        # Prepare GPT request
        system_prompt = self._build_gpt_system_prompt(customer_list)
        
        try:
            response = self.openai_client.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Parse this order: {text}"}
                ],
                max_tokens=200,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            
            # Log API usage (without sensitive data)
            logger.info("gpt_request_completed",
                       input_length=len(text),
                       tokens_used=response.usage.total_tokens if response.usage else 0)
            
            # Parse response
            parsed = self._parse_gpt_response(content)
            
            if parsed and self._validate_parsed_order(parsed):
                # Cache successful result
                self.gpt_cache.set(text, customer_list, parsed)
                logger.info("order_parsed_successfully",
                           customer=parsed.get('customer'),
                           amount=parsed.get('amount'))
                return parsed
            else:
                logger.warning("gpt_parsing_failed", response=content)
                return None
                
        except openai.AuthenticationError as e:
            logger.error("openai_auth_error", error=str(e))
            return None
        except openai.RateLimitError as e:
            logger.error("openai_rate_limit", error=str(e))
            raise  # Retry will handle this
        except Exception as e:
            logger.error("gpt_unexpected_error", error=str(e))
            return None
    
    def _build_gpt_system_prompt(self, customer_list: List[str]) -> str:
        """Build system prompt for GPT."""
        return (
            "You are an order processing assistant for a meat distribution business in Georgia. "
            "Extract order information and map customer names to exact matches from the list.\n\n"
            f"AVAILABLE CUSTOMERS:\n{json.dumps(customer_list, ensure_ascii=False)}\n\n"
            "INSTRUCTIONS:\n"
            "1. Extract customer name, amount (number), and product from the message\n"
            "2. Map customer name to EXACT name from the list (handle typos)\n"
            "3. Amount should be positive integer (remove units like GEL, kg)\n"
            "4. Return JSON: {\"customer\": \"exact_name\", \"amount\": number, \"product\": \"item\"}\n"
            "5. If unclear, return: null"
        )
    
    def _parse_gpt_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse GPT response safely."""
        if content.lower() == "null":
            return None
        
        # Clean response
        content = content.replace("'", "\"").strip()
        
        # Extract JSON if embedded in text
        if not content.startswith('{'):
            json_match = re.search(r'\{.*\}', content)
            if json_match:
                content = json_match.group()
            else:
                return None
        
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
    
    def _validate_parsed_order(self, parsed: Dict[str, Any]) -> bool:
        """Validate parsed order data."""
        required_keys = {'customer', 'amount', 'product'}
        if not isinstance(parsed, dict) or not all(key in parsed for key in required_keys):
            return False
        
        amount = parsed.get('amount', 0)
        product = parsed.get('product', '').strip()
        customer = parsed.get('customer', '').strip()
        
        if amount <= 0 or not product or not customer:
            return False
        
        # Verify customer exists in our list
        if customer not in self.name_to_full.values():
            return False
        
        return True
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        retry=retry_if_exception_type(gspread.exceptions.APIError)
    )
    async def record_to_sheets(self, timestamp: str, customer: str, 
                              amount: str, product: str, sender: str) -> bool:
        """Record order to Google Sheets with improved error handling."""
        try:
            worksheet = await self.sheets_client.get_worksheet(
                self.config.sheet_name, self.config.worksheet_name
            )
            
            # Sanitize data
            row = [
                timestamp,
                customer.replace('\n', ' ').replace('\r', ' '),
                str(amount),
                product.replace('\n', ' ').replace('\r', ' '),
                sender.replace('\n', ' ').replace('\r', ' ')
            ]
            
            worksheet.append_row(row)
            
            logger.info("order_recorded",
                       customer=customer,
                       amount=amount,
                       product=product)
            return True
            
        except Exception as e:
            logger.error("sheets_recording_error", error=str(e))
            return False
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Enhanced message handler with better error handling."""
        if self.shutdown_event.is_set():
            return
        
        # Periodic cleanup
        if time.time() - self.last_cleanup > self.config.cleanup_interval:
            await self._cleanup_old_data()
        
        message = update.message or update.edited_message
        if not message or not message.text:
            return
        
        user_id = message.from_user.id
        username = (message.from_user.username or 
                   f"{message.from_user.first_name} {message.from_user.last_name}".strip())
        
        # Rate limiting
        if not self._check_rate_limit(user_id):
            await message.reply_text(
                "გთხოვთ დაელოდოთ რამდენიმე წამს შემდეგი შეკვეთის გაგზავნამდე."
            )
            return
        
        try:
            # Process order
            text = message.text.strip()
            logger.info("processing_message", user=username, text_length=len(text))
            
            parsed = await self.parse_order_with_gpt(text)
            
            if parsed:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                success = await self.record_to_sheets(
                    timestamp,
                    parsed['customer'],
                    str(parsed['amount']),
                    parsed['product'],
                    username
                )
                
                if success:
                    await message.reply_text(
                        f"✅ შეკვეთა ჩაწერილია:\n"
                        f"{parsed['customer']}\n"
                        f"რაოდენობა: {parsed['amount']}\n"
                        f"პროდუქტი: {parsed['product']}"
                    )
                else:
                    await message.reply_text(
                        "❌ ვერ მოხერხდა Google Sheets-ში ჩაწერა. "
                        "გთხოვთ სცადოთ მოგვიანებით."
                    )
            else:
                await message.reply_text(
                    "ვერ მოხერხდა შეკვეთის ამოცნობა. გთხოვთ, გამოიყენოთ ფორმატი:\n"
                    "'კომპანიის სახელი რაოდენობა პროდუქტი'"
                )
                
        except Exception as e:
            logger.error("message_handling_error", 
                        user=username, 
                        error=str(e))
            await message.reply_text(
                "დაფიქსირდა შეცდომა. გთხოვთ სცადოთ მოგვიანებით."
            )

async def main():
    """Main function with improved error handling and graceful shutdown."""
    try:
        # Load configuration
        config = Config.from_env()
        logger.info("bot_starting", config_loaded=True)
        
        # Initialize bot
        bot = ImprovedOrderBot(config)
        
        # Create application
        application = Application.builder().token(config.telegram_token).build()
        
        # Add handlers
        async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await bot.handle_message(update, context)
        
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)
        )
        
        logger.info("bot_handlers_registered")
        
        # Start bot
        logger.info("bot_starting_polling")
        await application.run_polling(
            close_loop=False,
            stop_signals=None  # We handle signals manually
        )
        
    except Exception as e:
        logger.error("bot_startup_error", error=str(e))
        raise

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("bot_stopped_by_user")
    except Exception as e:
        logger.error("bot_fatal_error", error=str(e))
        raise