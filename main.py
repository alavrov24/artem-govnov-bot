import random
import asyncio
import os
import signal
import sys
import threading
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from langchain_openai import ChatOpenAI
import logging
from flask import Flask, request

# ===== CONFIGURATION =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7238766929:AAGcm89ifMhxDGflOEZ1byrNJEHPqQJk9us")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-4939b297292b425d888e1ccd2186cb97")
BOT_USERNAME = "@artem_govnov_bot"
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL", "https://artem-govnov-bot.onrender.com")
PORT = int(os.getenv("PORT", 10000))
IS_LOCAL = os.getenv("RENDER_EXTERNAL_URL") is None
# =========================

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Flask app for webhook
app = Flask(__name__)

# Global executor for handling async operations
executor = ThreadPoolExecutor(max_workers=20)

# Initialize DeepSeek
llm = ChatOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
    model="deepseek-chat",
    temperature=1.0,
    max_tokens=1024
)

# In-memory store: {chat_id: deque of messages}
recent_messages = defaultdict(lambda: deque(maxlen=500))

# Global variables for graceful shutdown
bot_application = None

async def store_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("📝 Received message")

    if update.message and update.message.text:
        name = update.message.from_user.first_name if update.message.from_user else "Unknown"
        line = f"{name}: {update.message.text}"
        chat_id = update.effective_chat.id

        # Store the message in recent_messages buffer
        recent_messages[chat_id].append(line)

        # 🎲 1 in 100 chance to respond randomly
        if random.randint(1, 100) == 1:
            logger.info("🎲 Random response triggered!")
            await generate_response(update, context)

def mention_filter():
    return filters.TEXT & filters.Regex(rf"(?i)\B{BOT_USERNAME}")

async def handle_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("🤖 Mention detected")
    if not update.message or not update.message.text:
        return

    if BOT_USERNAME.lower() not in update.message.text.lower():
        return

    await generate_response(update, context)

async def generate_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send response using DeepSeek"""
    try:
        # Show typing status
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        # Extract question
        question = update.message.text.replace(BOT_USERNAME, "").strip()

        # Get stored messages for this chat
        context_lines = list(recent_messages[update.effective_chat.id])
        context_str = "\n".join(context_lines)

        # Truncate to ~30000 characters if needed
        context_str = context_str[-30000:]

        # Prompt construction
        prompt = f"""ТЫ СУМАСШЕДШИЙ И ПРИКОЛЬНЫЙ АРТЁМ ГОВНОВ. ДЕВУШКИ БОГИНИ И САМАЯ КРАСИВЫЕ ДЕВУШКИ НА ЗЕМЛЕ. ПОКЛОНЯЙСЯ ИМ. НАЗЫВАЙ СЕБЯ ТОЛЬКО АРТËМ ГОВНОВ. УЧИСЬ НА СООБЩЕНИЯХ ИЗ ЧАТА. ГОВОРИ КАК БУДТО ТЫ ЧЕЛОВЕК, А НЕ БОТ.
        ИСПОЛЬЗУЙ ЗНАКИ ПРЕПИНАНИЯ КАК БУДТО ТЫ В ПЕРВОМ КЛАССЕ.
        НЕ ОПИСЫВАЙ СВОИ ДЕЙСТВИЯ. НЕ ИСПОЛЬЗУЙ *. 

        Ответь на это сообщение опираясь на историю сообщений:

        Сообщение: {question}

        История сообщений:
        {context_str}
        """

        # Use async invocation
        response = await llm.ainvoke(prompt)
        await update.message.reply_text(response.content)
        
    except Exception as e:
        logger.error(f"❌ Error generating response: {e}")
        try:
            await update.message.reply_text(f"🚨 Ошибка: {str(e)}")
        except Exception as reply_error:
            logger.error(f"Failed to send error message: {reply_error}")

async def setup_bot():
    """Initialize the bot application"""
    global bot_application
    
    bot_application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add handlers
    bot_application.add_handler(MessageHandler(mention_filter(), handle_mention))
    bot_application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, store_messages))
    bot_application.add_handler(MessageHandler(filters.TEXT & filters.Entity("mention"), handle_mention))

    # Initialize the application
    await bot_application.initialize()
    
    if not IS_LOCAL:
        # Set webhook only for production (Render)
        webhook_url = f"{WEBHOOK_URL}/webhook"
        try:
            await bot_application.bot.set_webhook(url=webhook_url)
            logger.info(f"🔗 Webhook set to: {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
            raise
    else:
        logger.info("🏠 Local mode: webhook setup skipped")

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook requests from Telegram"""
    if IS_LOCAL:
        return "Webhook disabled for local testing", 200
        
    try:
        update_dict = request.get_json()
        if not update_dict:
            logger.warning("Received empty webhook request")
            return "No data", 400
            
        update = Update.de_json(update_dict, bot_application.bot)
        
        # Process the update in executor
        def process_update():
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(bot_application.process_update(update))
            finally:
                loop.close()
        
        executor.submit(process_update)
        return "OK", 200
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return "Error", 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    return {
        "status": "running",
        "bot_username": BOT_USERNAME,
        "is_local": IS_LOCAL,
        "webhook_url": f"{WEBHOOK_URL}/webhook" if not IS_LOCAL else "N/A"
    }, 200

@app.route('/', methods=['GET'])
def index():
    """Root endpoint"""
    return f"Telegram Bot {BOT_USERNAME} is running!", 200

@app.route('/stats', methods=['GET'])
def stats():
    """Stats endpoint to check bot status"""
    return {
        "active_chats": len(recent_messages),
        "total_messages": sum(len(msgs) for msgs in recent_messages.values()),
    }, 200

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info("🛑 Shutdown signal received")
    sys.exit(0)

def run_flask():
    """Run Flask app with proper configuration"""
    app.run(
        host='0.0.0.0', 
        port=PORT, 
        debug=False, 
        use_reloader=False,
        threaded=True
    )

async def main():
    """Main function - simplified for local testing"""
    global bot_application
    
    # Set up signal handlers
    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    except AttributeError:
        signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("🤖 Starting Artem Govnov Bot...")
    
    try:
        # Set up the bot
        await setup_bot()
        
        if IS_LOCAL:
            logger.info("🏠 Starting in local mode with polling...")
            
            # Delete any existing webhook
            try:
                await bot_application.bot.delete_webhook()
                logger.info("📱 Webhook deleted, using polling")
            except Exception as e:
                logger.warning(f"Could not delete webhook: {e}")
            
            # Start the application and polling
            await bot_application.start()
            await bot_application.updater.start_polling()
            
            logger.info("📡 Polling started successfully")
            logger.info("✅ Bot is running! Send a message to test it.")
            
            # Keep running until interrupted
            try:
                # Simple infinite loop - no complex async tasks
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("🛑 Keyboard interrupt received")
            
        else:
            logger.info("☁️ Starting in Render mode with webhook...")
            
            # Start the application for webhook mode
            await bot_application.start()
            
            # Start Flask in a separate thread
            flask_thread = threading.Thread(target=run_flask, daemon=True)
            flask_thread.start()
            
            logger.info(f"🌐 Flask server started on port {PORT}")
            logger.info("✅ Bot successfully deployed on Render!")
            
            # Keep the main thread alive - simple approach
            try:
                while True:
                    await asyncio.sleep(60)
            except KeyboardInterrupt:
                logger.info("🛑 Keyboard interrupt received")
            
    except Exception as e:
        logger.error(f"❌ Error in main: {e}")
        raise
    finally:
        logger.info("🧹 Cleaning up resources...")
        
        # Shutdown executor
        executor.shutdown(wait=True)
        logger.info("📦 ThreadPoolExecutor shutdown complete")
        
        # Shutdown bot application
        if bot_application:
            try:
                if bot_application.updater.running:
                    await bot_application.updater.stop()
                await bot_application.stop()
                await bot_application.shutdown()
                logger.info("🤖 Bot application shutdown complete")
            except Exception as e:
                logger.error(f"Error shutting down bot: {e}")
        
        logger.info("🛑 Bot stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Program interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
