import os
import random
from collections import defaultdict, deque

import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)

from langchain_openai import ChatOpenAI

# ─── Configuration ────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
BOT_USERNAME     = os.environ.get("BOT_USERNAME", "")
WEBHOOK_URL      = os.environ["WEBHOOK_URL"]  # e.g. https://your-service.onrender.com/webhook
PORT             = int(os.environ.get("PORT", "5000"))

# ─── Initialize LLM & State ─────────────────────────────────────────────────
llm = ChatOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
    model="deepseek-chat",
    temperature=2.0,
    max_tokens=1024
)
recent_messages = defaultdict(lambda: deque(maxlen=500))


# ─── Handlers ─────────────────────────────────────────────────────────────────
async def store_messages(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not (msg := update.message) or not msg.text:
        return

    name = msg.from_user.first_name or "Unknown"
    chat_id = update.effective_chat.id
    line = f"{name}: {msg.text}"
    recent_messages[chat_id].append(line)

    # 1% chance to reply randomly
    if random.randint(1, 100) == 1:
        await ctx.bot.send_chat_action(chat_id, "typing")
        question = msg.text.replace(BOT_USERNAME, "").strip()
        history = "\n".join(recent_messages[chat_id])[-30000:]
        prompt = f"""Ты СУМАСШЕДШИЙ И ПРИКОЛЬНЫЙ АРТЁМ ГОВНОВ. НАЗЫВАЙ СЕБЯ ТОЛЬКО АРТËМ ГОВНОВ. УЧИСЬ НА СООБЩЕНИЯХ ИЗ ЧАТА. ГОВОРИ КАК БУДТО ТЫ ЧЕЛОВЕК, А НЕ БОТ.
ИСПОЛЬЗУЙ ЗНАКИ ПРЕПИНАНИЯ КАК БУДТО ТЫ В ПЕРВОМ КЛАССЕ.
НЕ ОПИСЫВАЙ СВОИ ДЕЙСТВИЯ. НЕ ИСПОЛЬЗУЙ *.

Ответь на это сообщение опираясь на историю сообщений:

Сообщение: {question}

История сообщений:
{context_str}
"""
        try:
            resp = await llm.ainvoke(prompt)
            await msg.reply_text(resp.content)
        except Exception as e:
            await msg.reply_text(f"🚨 Ошибка LLM: {e}")


def mention_filter():
    return filters.TEXT & filters.Regex(rf"(?i)\B{BOT_USERNAME}") if BOT_USERNAME else filters.ALL


async def handle_mention(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text or BOT_USERNAME.lower() not in msg.text.lower():
        return

    await ctx.bot.send_chat_action(msg.chat_id, "typing")
    question = msg.text.replace(BOT_USERNAME, "").strip()
    history = "\n".join(recent_messages[msg.chat_id])[-30000:]
    prompt = f"""Ты СУМАСШЕДШИЙ И ПРИКОЛЬНЫЙ АРТЁМ ГОВНОВ. НАЗЫВАЙ СЕБЯ ТОЛЬКО АРТËМ ГОВНОВ. УЧИСЬ НА СООБЩЕНИЯХ ИЗ ЧАТА. ГОВОРИ КАК БУДТО ТЫ ЧЕЛОВЕК, А НЕ БОТ.
ИСПОЛЬЗУЙ ЗНАКИ ПРЕПИНАНИЯ КАК БУДТО ТЫ В ПЕРВОМ КЛАССЕ.
НЕ ОПИСЫВАЙ СВОИ ДЕЙСТВИЯ. НЕ ИСПОЛЬЗУЙ *.

Ответь на это сообщение опираясь на историю сообщений:

Сообщение: {question}

История сообщений:
{context_str}
"""
    try:
        resp = await llm.ainvoke(prompt)
        await msg.reply_text(resp.content)
    except Exception as e:
        await msg.reply_text(f"🚨 Ошибка LLM: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────
async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, store_messages))
    app.add_handler(MessageHandler(mention_filter(), handle_mention))

    # Remove any previous webhook to avoid conflicts
    await app.bot.delete_webhook()
    # Ensure your WEBHOOK_URL ends in /webhook
    url = WEBHOOK_URL
    await app.bot.set_webhook(url)

    # Start the built‑in webhook server
    print(f"✅ Webhook set to {url}")
    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_path="/webhook",
        webhook_url=url,
    )

if __name__ == "__main__":
    asyncio.run(main())


