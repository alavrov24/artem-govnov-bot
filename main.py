import os
import random
from collections import defaultdict, deque

from flask import Flask, request
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from langchain_openai import ChatOpenAI

# ===== CONFIGURATION =====
TELEGRAM_TOKEN = "7238766929:AAGcm89ifMhxDGflOEZ1byrNJEHPqQJk9us"    
DEEPSEEK_API_KEY = "sk-4939b297292b425d888e1ccd2186cb97"
BOT_USERNAME = "@artem_govnov_bot" 

# Initialize DeepSeek/OpenAI LLM
llm = ChatOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
    model="deepseek-chat",
    temperature=1.5,
    max_tokens=1024
)

# In-memory store: {chat_id: deque of messages}
recent_messages = defaultdict(lambda: deque(maxlen=500))


async def store_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("📝 Received message")
    if update.message and update.message.text:
        name = update.message.from_user.first_name if update.message.from_user else "Unknown"
        line = f"{name}: {update.message.text}"
        chat_id = update.effective_chat.id

        # Store the message in recent_messages buffer
        recent_messages[chat_id].append(line)

        # 🎲 1 in 100 chance to respond randomly
        if random.randint(1, 100) == 1:
            print("🎲 Random response triggered!")
            # Show typing status
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")

            # Extract question (remove bot username if present)
            question = update.message.text.replace(BOT_USERNAME, "").strip()
            # Get stored messages for this chat
            context_lines = list(recent_messages[chat_id])
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
                # Use async invocation
                response = await llm.ainvoke(prompt)
                await update.message.reply_text(response.content)
            except Exception as e:
                print("❌ LangChain error:", e)
                await update.message.reply_text(f"🚨 Ошибка: {str(e)}")


def mention_filter():
    # Filter for messages containing the bot username
    if BOT_USERNAME:
        return filters.TEXT & filters.Regex(rf"(?i)\B{BOT_USERNAME}")
    else:
        # If BOT_USERNAME not set, match nothing
        return filters.TEXT & filters.Regex(r"$^")


async def handle_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🤖 Mention detected")
    if not update.message or not update.message.text:
        return
    if BOT_USERNAME.lower() not in update.message.text.lower():
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    # Extract question (remove bot username)
    question = update.message.text.replace(BOT_USERNAME, "").strip()
    # Get stored messages for this chat
    context_lines = list(recent_messages[update.effective_chat.id])
    context_str = "\n".join(context_lines)
    context_str = context_str[-30000:]  # truncate if needed

    prompt = f"""Ты СУМАСШЕДШИЙ И ПРИКОЛЬНЫЙ АРТЁМ ГОВНОВ. НАЗЫВАЙ СЕБЯ ТОЛЬКО АРТËМ ГОВНОВ. УЧИСЬ НА СООБЩЕНИЯХ ИЗ ЧАТА. ГОВОРИ КАК БУДТО ТЫ ЧЕЛОВЕК, А НЕ БОТ.
ИСПОЛЬЗУЙ ЗНАКИ ПРЕПИНАНИЯ КАК БУДТО ТЫ В ПЕРВОМ КЛАССЕ.
НЕ ОПИСЫВАЙ СВОИ ДЕЙСТВИЯ. НЕ ИСПОЛЬЗУЙ *.

Ответь на это сообщение опираясь на историю сообщений:

Сообщение: {question}

История сообщений:
{context_str}
"""
    try:
        response = await llm.ainvoke(prompt)
        await update.message.reply_text(response.content)
    except Exception as e:
        print("❌ LangChain error:", e)
        await update.message.reply_text(f"🚨 Ошибка: {str(e)}")


# Initialize Flask app and Telegram application
app = Flask(__name__)
application = Application.builder().token(TELEGRAM_TOKEN).build()

# Register handlers
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, store_messages))
application.add_handler(MessageHandler(mention_filter(), handle_mention))
application.add_handler(MessageHandler(filters.TEXT & filters.Entity("mention"), handle_mention))


@app.route("/webhook", methods=["POST"])
async def webhook():
    if request.headers.get("Content-Type") == "application/json":
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        # Process update
        async with application:
            await application.process_update(update)
        return "", 200
    return "", 400


def main():
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        print("Error: WEBHOOK_URL environment variable not set")
        return

    import asyncio
    # Optional: delete existing webhook to avoid conflicts
    asyncio.run(application.bot.delete_webhook())
    # Ensure the URL ends with /webhook
    if not webhook_url.endswith("/webhook"):
        webhook_url = webhook_url.rstrip("/") + "/webhook"
    asyncio.run(application.bot.set_webhook(url=webhook_url))
    print(f"Webhook URL set to {webhook_url}")

    # Start Flask server (useful if running directly, or use Gunicorn in production)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))


if __name__ == "__main__":
    main()

