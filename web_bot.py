import asyncio
import html
import logging
import os
from datetime import datetime, timedelta

import httpx
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from db import (
    init_db,
    save_mailbox,
    get_mailbox,
    delete_mailbox,
    get_all_mailboxes,
    update_last_seen_message,
)
from mailtm import MailTMClient, create_new_mailbox

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN")
if not BASE_URL:
    raise RuntimeError("Не найден RENDER_EXTERNAL_URL")

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = BASE_URL.rstrip("/") + WEBHOOK_PATH

logging.basicConfig(level=logging.INFO)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📬 Новая почта"), KeyboardButton(text="📭 Моя почта")],
            [KeyboardButton(text="📥 Входящие"), KeyboardButton(text="🗑 Удалить ящик")],
            [KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


def inbox_refresh_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить входящие", callback_data="refresh_inbox")]
        ]
    )


def format_mail_time(iso_time: str) -> str:
    if not iso_time:
        return "неизвестно"

    try:
        dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
        dt = dt.replace(tzinfo=None)
        dt = dt + timedelta(hours=4)
        return dt.strftime("%d.%m %H:%M")
    except Exception:
        return iso_time


def format_mail_preview(full_msg):
    sender = full_msg.get("from", {}).get("address", "unknown")
    subject = full_msg.get("subject") or "(без темы)"
    created_at = format_mail_time(full_msg.get("createdAt"))
    text = (full_msg.get("text") or full_msg.get("intro") or "Текст письма пуст").strip()

    short_text = text[:500]
    if len(text) > 500:
        short_text += "..."

    return (
        f"📨 <b>Письмо</b>\n"
        f"👤 <b>От:</b> {html.escape(sender)}\n"
        f"📝 <b>Тема:</b> {html.escape(subject)}\n"
        f"🕒 <b>Получено:</b> {html.escape(created_at)}\n\n"
        f"{html.escape(short_text)}"
    )


async def send_inbox(message: Message):
    box = get_mailbox(message.from_user.id)
    if not box:
        await message.answer(
            "Сначала создай почту кнопкой «📬 Новая почта» или командой /newmail",
            reply_markup=main_menu(),
        )
        return

    try:
        api = MailTMClient()
        messages = api.get_messages(box["token"])

        if not messages:
            await message.answer(
                "Во входящих пока пусто.",
                reply_markup=main_menu(),
            )
            return

        result = []
        for msg in messages[:5]:
            msg_id = msg.get("id", "unknown")
            full_msg = api.get_message(box["token"], msg_id)
            result.append(format_mail_preview(full_msg))

        text = "\n\n────────────\n\n".join(result)

        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=inbox_refresh_kb(),
        )

    except httpx.HTTPStatusError as e:
        status = e.response.status_code

        if status == 401:
            await message.answer(
                "Не удалось открыть входящие. Похоже, токен ящика устарел. Создай новую почту.",
                reply_markup=main_menu(),
            )
        elif status == 429:
            await message.answer(
                "Слишком много запросов подряд. Подожди пару секунд и попробуй снова.",
                reply_markup=main_menu(),
            )
        else:
            await message.answer(
                f"Ошибка при загрузке входящих: {html.escape(str(e))}",
                reply_markup=main_menu(),
            )
    except Exception as e:
        await message.answer(
            f"Не удалось открыть входящие: {html.escape(str(e))}",
            reply_markup=main_menu(),
        )


async def check_new_messages_loop():
    await asyncio.sleep(5)
    while True:
        try:
            api = MailTMClient()
            mailboxes = get_all_mailboxes()

            for box in mailboxes:
                try:
                    messages = api.get_messages(box["token"])
                    if not messages:
                        continue

                    latest = messages[0]
                    latest_id = latest.get("id")

                    if not latest_id:
                        continue

                    if box.get("last_seen_message_id") == latest_id:
                        continue

                    full_msg = api.get_message(box["token"], latest_id)

                    preview = format_mail_preview(full_msg)
                    await bot.send_message(
                        box["user_id"],
                        f"🔔 <b>Новое письмо</b>\n\n{preview}",
                        parse_mode="HTML",
                    )

                    update_last_seen_message(box["user_id"], latest_id)

                except Exception:
                    continue

        except Exception:
            pass

        await asyncio.sleep(10)


@dp.message(Command("start"))
async def start_cmd(message: Message):
    text = (
        "Привет. Я бот для временной почты\n\n"
        "Что я умею:\n"
        "• создать случайную почту\n"
        "• создать почту со своим именем\n"
        "• показать последние 5 писем\n"
        "• быстро обновить входящие\n"
        "• автоматически прислать новое письмо в Telegram\n\n"
        "Команды:\n"
        "/newmail — случайная почта\n"
        "/newmail ИМЯ ПАРОЛЬ — создать почту со своим именем\n"
        "/mymail — показать текущую почту\n"
        "/inbox — показать последние 5 писем\n"
        "/read ID — открыть письмо по ID\n"
        "/deletebox — удалить текущий ящик\n\n"
        "Либо просто пользуйся кнопками снизу."
    )
    await message.answer(text, reply_markup=main_menu())


@dp.message(Command("newmail"))
async def newmail_cmd(message: Message):
    try:
        parts = message.text.split()

        custom_name = None
        custom_password = None

        if len(parts) >= 2:
            custom_name = parts[1].strip().lower()

        if len(parts) >= 3:
            custom_password = parts[2].strip()

        if custom_name:
            allowed = "abcdefghijklmnopqrstuvwxyz0123456789._-"
            if any(ch not in allowed for ch in custom_name):
                await message.answer(
                    "Имя почты может содержать только латинские буквы, цифры, точку, дефис и нижнее подчёркивание.",
                    reply_markup=main_menu(),
                )
                return

        if custom_password and len(custom_password) < 6:
            await message.answer(
                "Пароль должен быть минимум 6 символов.",
                reply_markup=main_menu(),
            )
            return

        box = create_new_mailbox(
            custom_name=custom_name,
            custom_password=custom_password,
        )

        save_mailbox(
            user_id=message.from_user.id,
            account_id=box["id"],
            address=box["address"],
            password=box["password"],
            token=box["token"],
        )

        await message.answer(
            f"✅ <b>Новая почта создана</b>\n\n"
            f"📧 <b>Адрес:</b>\n<code>{html.escape(box['address'])}</code>\n\n"
            f"🔑 <b>Пароль:</b>\n<code>{html.escape(box['password'])}</code>",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )

    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        response_text = e.response.text.lower()

        if status == 422:
            if "address" in response_text:
                await message.answer(
                    "Такое имя почты уже занято или адрес некорректный. Попробуй другое имя.",
                    reply_markup=main_menu(),
                )
            elif "password" in response_text:
                await message.answer(
                    "Не подошёл пароль. Попробуй другой пароль подлиннее.",
                    reply_markup=main_menu(),
                )
            else:
                await message.answer(
                    "Не удалось создать почту. Проверь имя и пароль.",
                    reply_markup=main_menu(),
                )
        elif status == 429:
            await message.answer(
                "Слишком много запросов подряд. Подожди пару секунд и попробуй ещё раз.",
                reply_markup=main_menu(),
            )
        else:
            await message.answer(
                f"Ошибка создания почты: {html.escape(str(e))}",
                reply_markup=main_menu(),
            )
    except Exception as e:
        await message.answer(
            f"Не удалось создать почту: {html.escape(str(e))}",
            reply_markup=main_menu(),
        )


@dp.message(Command("mymail"))
async def mymail_cmd(message: Message):
    box = get_mailbox(message.from_user.id)
    if not box:
        await message.answer(
            "У тебя ещё нет активной почты. Нажми «📬 Новая почта».",
            reply_markup=main_menu(),
        )
        return

    await message.answer(
        f"📧 <b>Текущая почта:</b>\n<code>{html.escape(box['address'])}</code>",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


@dp.message(Command("inbox"))
async def inbox_cmd(message: Message):
    await send_inbox(message)


@dp.callback_query(F.data == "refresh_inbox")
async def refresh_inbox_callback(callback: CallbackQuery):
    box = get_mailbox(callback.from_user.id)
    if not box:
        await callback.answer("Сначала создай почту", show_alert=True)
        return

    try:
        api = MailTMClient()
        messages = api.get_messages(box["token"])

        if not messages:
            await callback.message.edit_text(
                "Во входящих пока пусто.",
                reply_markup=inbox_refresh_kb(),
            )
            await callback.answer("Обновлено")
            return

        result = []
        for msg in messages[:5]:
            msg_id = msg.get("id", "unknown")
            full_msg = api.get_message(box["token"], msg_id)
            result.append(format_mail_preview(full_msg))

        text = "\n\n────────────\n\n".join(result)

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=inbox_refresh_kb(),
        )
        await callback.answer("Входящие обновлены")

    except Exception:
        await callback.answer("Не удалось обновить входящие", show_alert=True)


@dp.message(Command("read"))
async def read_cmd(message: Message):
    box = get_mailbox(message.from_user.id)
    if not box:
        await message.answer(
            "Сначала создай почту кнопкой «📬 Новая почта».",
            reply_markup=main_menu(),
        )
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Использование: /read ID\n\nПример:\n/read 123456789",
            reply_markup=main_menu(),
        )
        return

    message_id = parts[1].strip()

    try:
        api = MailTMClient()
        msg = api.get_message(box["token"], message_id)

        sender = msg.get("from", {}).get("address", "unknown")
        subject = msg.get("subject") or "(без темы)"
        created_at = format_mail_time(msg.get("createdAt"))
        text = msg.get("text") or msg.get("intro") or "Текст письма пуст"

        reply = (
            f"📨 <b>Полное письмо</b>\n"
            f"👤 <b>От:</b> {html.escape(sender)}\n"
            f"📝 <b>Тема:</b> {html.escape(subject)}\n"
            f"🕒 <b>Получено:</b> {html.escape(created_at)}\n\n"
            f"{html.escape(text[:3500])}"
        )
        await message.answer(reply, parse_mode="HTML", reply_markup=main_menu())

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            await message.answer(
                "Письмо с таким ID не найдено.",
                reply_markup=main_menu(),
            )
        else:
            await message.answer(
                f"Ошибка чтения письма: {html.escape(str(e))}",
                reply_markup=main_menu(),
            )
    except Exception as e:
        await message.answer(
            f"Не удалось открыть письмо: {html.escape(str(e))}",
            reply_markup=main_menu(),
        )


@dp.message(Command("deletebox"))
async def deletebox_cmd(message: Message):
    box = get_mailbox(message.from_user.id)
    if not box:
        await message.answer(
            "У тебя нет активного ящика.",
            reply_markup=main_menu(),
        )
        return

    delete_mailbox(message.from_user.id)
    await message.answer(
        "🗑 Текущий ящик удалён из бота.\n\nСоздать новый можно кнопкой «📬 Новая почта».",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "📬 Новая почта")
async def newmail_button(message: Message):
    await message.answer(
        "Чтобы создать случайную почту, отправь:\n/newmail\n\n"
        "Чтобы создать почту со своим именем и паролем, отправь:\n"
        "/newmail моёимя мойпароль123",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "📭 Моя почта")
async def mymail_button(message: Message):
    await mymail_cmd(message)


@dp.message(F.text == "📥 Входящие")
async def inbox_button(message: Message):
    await send_inbox(message)


@dp.message(F.text == "🗑 Удалить ящик")
async def deletebox_button(message: Message):
    await deletebox_cmd(message)


@dp.message(F.text == "ℹ️ Помощь")
async def help_button(message: Message):
    await message.answer(
        "Подсказка:\n\n"
        "• /newmail — случайная почта\n"
        "• /newmail ИМЯ ПАРОЛЬ — своя почта\n"
        "• /mymail — текущий адрес\n"
        "• /inbox — последние 5 писем\n"
        "• /read ID — открыть письмо по ID\n"
        "• /deletebox — удалить ящик\n\n"
        "Новые письма бот старается присылать автоматически.",
        reply_markup=main_menu(),
    )


@dp.message()
async def fallback_handler(message: Message):
    await message.answer(
        "Я не понял сообщение.\n\nНажми кнопку снизу или используй /start",
        reply_markup=main_menu(),
    )


async def on_startup(app):
    init_db()
    await bot.set_webhook(
        WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
    )
    app["mail_loop"] = asyncio.create_task(check_new_messages_loop())
    logging.info("Webhook set: %s", WEBHOOK_URL)


async def on_shutdown(app):
    task = app.get("mail_loop")
    if task:
        task.cancel()
    await bot.delete_webhook()
    await bot.session.close()


def create_app():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
    ).register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)

    async def health(request):
        return web.Response(text="ok")

    app.router.add_get("/", health)
    app.router.add_get("/healthz", health)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=PORT)
