import random
import asyncio
from collections import defaultdict, deque
from aiohttp import web  # лёгкий веб-сервер
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from langchain_openai import ChatOpenAI

# ===== CONFIGURATION =====
TELEGRAM_TOKEN = "7238766929:AAGcm89ifMhxDGflOEZ1byrNJEHPqQJk9us"
DEEPSEEK_API_KEY = "sk-4939b297292b425d888e1ccd2186cb97"
BOT_USERNAME = "@artem_govnov_bot"
# =========================

# Initialize DeepSeek
llm = ChatOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
    model="deepseek-chat",
    temperature=2.0,
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
        recent_messages[chat_id].append(line)

        # 🎲 1 in 100 chance to respond randomly
        if random.randint(1, 100) == 1:
            print("🎲 Random response triggered!")
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            question = update.message.text.replace(BOT_USERNAME, "").strip()
            context_lines = list(recent_messages[chat_id])
            context_str = "\n".join(context_lines)[-30000:]

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


def mention_filter():
    return filters.TEXT & filters.Regex(rf"(?i)\B{BOT_USERNAME}")


async def handle_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🤖 Mention detected")
    if not update.message or not update.message.text:
        return

    if BOT_USERNAME.lower() not in update.message.text.lower():
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    question = update.message.text.replace(BOT_USERNAME, "").strip()
    context_lines = list(recent_messages[update.effective_chat.id])
    context_str = "\n".join(context_lines)[-30000:]

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


# --- HTTP сервер для Render ---
async def handle_http(request):
    return web.Response(text="Bot is running")

async def start_http_server():
    app = web.Application()
    app.add_routes([web.get('/', handle_http)])
    runner = web.AppRunner(app)
    await runner.setup()
    # Используем порт из env Render, либо 10000 по умолчанию
    import os
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 HTTP server running on port {port}")


async def main():
    # Запускаем HTTP сервер параллельно с ботом
    await start_http_server()

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(mention_filter(), handle_mention))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, store_messages))
    application.add_handler(MessageHandler(filters.TEXT & filters.Entity("mention"), handle_mention))

    await application.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
