import asyncio
import logging
from typing import Dict, List

from openai import OpenAI
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=config.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

user_histories: Dict[int, List[dict]] = {}

SYSTEM_PROMPT = (
    "You are a helpful Telegram assistant. "
    "Answer clearly and naturally. "
    "Keep formatting simple for Telegram."
)


def get_history(user_id: int) -> List[dict]:
    if user_id not in user_histories:
        user_histories[user_id] = []
    return user_histories[user_id]


def trim_history(history: List[dict]) -> None:
    max_items = max(2, config.MAX_HISTORY_MESSAGES)
    if len(history) > max_items:
        del history[:-max_items]


def response_to_text(resp) -> str:
    if hasattr(resp, "choices") and resp.choices:
        message = getattr(resp.choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content.strip() or "Не получилось получить текстовый ответ."
    return "Не получилось получить текстовый ответ."


def build_text_messages(history: List[dict], user_text: str):
    items = [{"role": "system", "content": SYSTEM_PROMPT}]
    items.extend(history)
    items.append({"role": "user", "content": user_text})
    return items


def ask_groq_text(history: List[dict], user_text: str) -> str:
    resp = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=build_text_messages(history, user_text),
    )
    return response_to_text(resp)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет. Я Telegram-бот на Groq.\n\n"
        "Что умею:\n"
        "- обычный чат\n"
        "- новый диалог: /new\n\n"
        "Важно: генерация картинок и ответы по фото тут отключены."
    )
    await update.message.reply_text(text)


async def new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_histories[update.effective_user.id] = []
    await update.message.reply_text("История очищена. Начали новый диалог.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = update.effective_user.id
    user_text = (message.text or "").strip()
    if not user_text:
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    history = get_history(user_id)

    try:
        answer = await asyncio.to_thread(ask_groq_text, history, user_text)
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": answer})
        trim_history(history)
        await message.reply_text(answer)
    except Exception as e:
        logger.exception("Text request failed")
        await message.reply_text(f"Ошибка ответа: {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Этот вариант бота на Groq пока работает только с текстом, без фото.")


async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Генерация картинок отключена, потому что этот бот сейчас переведён на Groq.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start — запуск\n"
        "/new — новый диалог\n\n"
        "Также можешь просто писать текст. Фото и /image сейчас отключены."
    )


def main():
    if "PASTE_" in config.TELEGRAM_BOT_TOKEN or "PASTE_" in config.GROQ_API_KEY:
        raise RuntimeError("Заполни TELEGRAM_BOT_TOKEN и GROQ_API_KEY в config.py")

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("new", new_chat))
    app.add_handler(CommandHandler("image", image_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
