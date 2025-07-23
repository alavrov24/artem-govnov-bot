import asyncio
import random
from collections import defaultdict, deque
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from langchain_openai import ChatOpenAI

# ===== CONFIGURATION =====
TELEGRAM_TOKEN = "7238766929:AAGcm89ifMhxDGflOEZ1byrNJEHPqQJk9us"     # From @BotFather
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

        # Store the message in recent_messages buffer
        recent_messages[chat_id].append(line)

        # 🎲 1 in 100 chance to respond randomly
        if random.randint(1, 100) == 1:
            print("🎲 Random response triggered!")

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
                #await update.message.reply_text("✅ Mention detected! (LLM call skipped)")
            except Exception as e:
                print("❌ LangChain error:", e)
                await update.message.reply_text(f"🚨 Ошибка: {str(e)}")


def mention_filter():
    return filters.TEXT & filters.Regex(rf"(?i)\B{BOT_USERNAME}")

async def handle_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🤖 Mention detected")
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
        #await update.message.reply_text("✅ Mention detected! (LLM call skipped)")
    except Exception as e:
        print("❌ LangChain error:", e)
        await update.message.reply_text(f"🚨 Ошибка: {str(e)}")


def main():
    print("🤖 Запуск бота Артёма Говнова...")
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(MessageHandler(mention_filter(), handle_mention))

    # Store all messages (for context history)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, store_messages))

    # Handle bot mentions
    application.add_handler(MessageHandler(filters.TEXT & filters.Entity("mention"), handle_mention))

    # Start polling
    application.run_polling()
    print("🛑 Бот остановлен")


if __name__ == "__main__":
    main()