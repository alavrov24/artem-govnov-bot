import random
import asyncio
import os
from collections import defaultdict, deque
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from langchain_openai import ChatOpenAI
import logging
from flask import Flask, request
import threading

# ===== CONFIGURATION =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7238766929:AAGcm89ifMhxDGflOEZ1byrNJEHPqQJk9us")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-4939b297292b425d888e1ccd2186cb97")
BOT_USERNAME = "@artem_govnov_bot"
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL", "https://artem-govnov-bot.onrender.com")  
PORT = int(os.getenv("PORT", 10000))  # Render uses this port
# =========================

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Flask app for webhook
app = Flask(__name__)

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

# Global bot application
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
    
            try:
                # Use async invocation if supported
                response = await llm.ainvoke(prompt)
                await update.message.reply_text(response.content)
            except Exception as e:
                logger.error(f"❌ LangChain error: {e}")
                await update.message.reply_text(f"🚨 Ошибка: {str(e)}")

def mention_filter():
    return filters.TEXT & filters.Regex(rf"(?i)\B{BOT_USERNAME}")

async def handle_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("🤖 Mention detected")
    """Handles mentions of the bot and replies based on message history."""
    if not update.message or not update.message.text:
        return

    if BOT_USERNAME.lower() not in update.message.text.lower():
        return

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
    prompt = f"""Ты СУМАСШЕДШИЙ И ПРИКОЛЬНЫЙ АРТЁМ ГОВНОВ. НАЗЫВАЙ СЕБЯ ТОЛЬКО АРТËМ ГОВНОВ. УЧИСЬ НА СООБЩЕНИЯХ ИЗ ЧАТА. ГОВОРИ КАК БУДТО ТЫ ЧЕЛОВЕК, А НЕ БОТ.
    ИСПОЛЬЗУЙ ЗНАКИ ПРЕПИНАНИЯ КАК БУДТО ТЫ В ПЕРВОМ КЛАССЕ.
    НЕ ОПИСЫВАЙ СВОИ ДЕЙСТВИЯ. НЕ ИСПОЛЬЗУЙ *. 

    Ответь на это сообщение опираясь на историю сообщений:

    Сообщение: {question}

    История сообщений:
    {context_str}
    """
    
    try:
        # Use async invocation if supported
        response = await llm.ainvoke(prompt)
        await update.message.reply_text(response.content)
    except Exception as e:
        logger.error(f"❌ LangChain error: {e}")
        await update.message.reply_text(f"🚨 Ошибка: {str(e)}")

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
    
    # Set webhook
    webhook_url = f"{WEBHOOK_URL}/webhook"
    await bot_application.bot.set_webhook(url=webhook_url)
    logger.info(f"🔗 Webhook set to: {webhook_url}")

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook requests from Telegram"""
    try:
        # Get the update from Telegram
        update_dict = request.get_json()
        update = Update.de_json(update_dict, bot_application.bot)
        
        # Process the update asynchronously
        asyncio.create_task(bot_application.process_update(update))
        
        return "OK", 200
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return "Error", 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    return "Bot is running!", 200

@app.route('/', methods=['GET'])
def index():
    """Root endpoint"""
    return "Telegram Bot is running on Render!", 200

def run_flask():
    """Run Flask app"""
    app.run(host='0.0.0.0', port=PORT)

async def main():
    """Main function to set up the bot"""
    logger.info("🤖 Запуск бота Артёма Говнова на Render...")
    
    try:
        # Set up the bot
        await setup_bot()
        
        # Start Flask in a separate thread
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        logger.info(f"🌐 Flask server started on port {PORT}")
        logger.info("✅ Bot successfully deployed on Render!")
        
        # Keep the main thread alive
        while True:
            await asyncio.sleep(60)
            
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
    finally:
        if bot_application:
            await bot_application.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
