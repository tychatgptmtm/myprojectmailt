import asyncio
import html
import logging
import os
from datetime import datetime, timedelta

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from db import (
    delete_mailbox,
    get_all_mailboxes,
    get_mailbox,
    init_db,
    save_mailbox,
    update_last_seen_message,
)
from mailtm import MailTMClient, create_new_mailbox

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "10"))
TIME_SHIFT_HOURS = int(os.getenv("TIME_SHIFT_HOURS", "4"))

if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
mail_loop_task = None


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📬 Новая почта"), KeyboardButton(text="📭 Моя почта")],
            [KeyboardButton(text="📥 Входящие"), KeyboardButton(text="🗑 Удалить ящик")],
            [KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
    )


def inbox_refresh_kb() -> InlineKeyboardMarkup:
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
        dt = dt + timedelta(hours=TIME_SHIFT_HOURS)
        return dt.strftime("%d.%m %H:%M")
    except Exception:
        return iso_time


def format_mail_preview(full_msg: dict) -> str:
    sender = full_msg.get("from", {}).get("address", "unknown")
    subject = full_msg.get("subject") or "(без темы)"
    created_at = format_mail_time(full_msg.get("createdAt"))
    text = (full_msg.get("text") or full_msg.get("intro") or "Текст письма пуст").strip()
    short_text = text[:500]
    if len(text) > 500:
        short_text += "..."

    return (
        f"📩 Письмо\n"
        f"От: {html.escape(sender)}\n"
        f"Тема: {html.escape(subject)}\n"
        f"Получено: {html.escape(created_at)}\n\n"
        f"{html.escape(short_text)}"
    )


async def send_inbox(message: Message) -> None:
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
            await message.answer("Во входящих пока пусто.", reply_markup=main_menu())
            return

        result = []
        for msg in messages[:5]:
            msg_id = msg.get("id", "unknown")
            full_msg = api.get_message(box["token"], msg_id)
            result.append(format_mail_preview(full_msg))

        text = "\n\n────────────\n\n".join(result)
        await message.answer(text, parse_mode="HTML", reply_markup=inbox_refresh_kb())
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


async def check_new_messages_loop() -> None:
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
                        f"📨 Новое письмо\n\n{preview}",
                        parse_mode="HTML",
                    )
                    update_last_seen_message(box["user_id"], latest_id)
                except Exception:
                    continue
        except Exception:
            pass

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


@dp.message(Command("start"))
async def start_cmd(message: Message) -> None:
    text = (
        "Привет.\n"
        "Я бот для временной почты\n\n"
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
async def newmail_cmd(message: Message) -> None:
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

        box = create_new_mailbox(custom_name=custom_name, custom_password=custom_password)
        save_mailbox(
            user_id=message.from_user.id,
            account_id=box["id"],
            address=box["address"],
            password=box["password"],
            token=box["token"],
        )
        await message.answer(
            f"✅ Новая почта создана\n\n"
            f"📮 Адрес:\n{html.escape(box['address'])}\n\n"
            f"🔑 Пароль:\n{html.escape(box['password'])}",
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
async def mymail_cmd(message: Message) -> None:
    box = get_mailbox(message.from_user.id)
    if not box:
        await message.answer(
            "У тебя ещё нет активной почты. Нажми «📬 Новая почта».",
            reply_markup=main_menu(),
        )
        return

    await message.answer(
        f"📭 Текущая почта:\n{html.escape(box['address'])}",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


@dp.message(Command("inbox"))
async def inbox_cmd(message: Message) -> None:
    await send_inbox(message)


@dp.callback_query(F.data == "refresh_inbox")
async def refresh_inbox_callback(callback: CallbackQuery) -> None:
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
async def read_cmd(message: Message) -> None:
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
            f"📨 Полное письмо\n"
            f"От: {html.escape(sender)}\n"
            f"Тема: {html.escape(subject)}\n"
            f"Получено: {html.escape(created_at)}\n\n"
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
async def deletebox_cmd(message: Message) -> None:
    box = get_mailbox(message.from_user.id)
    if not box:
        await message.answer("У тебя нет активного ящика.", reply_markup=main_menu())
        return

    delete_mailbox(message.from_user.id)
    await message.answer(
        "🗑 Текущий ящик удалён из бота.\n\nСоздать новый можно кнопкой «📬 Новая почта».",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "📬 Новая почта")
async def newmail_button(message: Message) -> None:
    await message.answer(
        "Чтобы создать случайную почту, отправь:\n/newmail\n\n"
        "Чтобы создать почту со своим именем и паролем, отправь:\n"
        "/newmail моеимя мойпароль123",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "📭 Моя почта")
async def mymail_button(message: Message) -> None:
    await mymail_cmd(message)


@dp.message(F.text == "📥 Входящие")
async def inbox_button(message: Message) -> None:
    await send_inbox(message)


@dp.message(F.text == "🗑 Удалить ящик")
async def deletebox_button(message: Message) -> None:
    await deletebox_cmd(message)


@dp.message(F.text == "ℹ️ Помощь")
async def help_button(message: Message) -> None:
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
async def fallback_handler(message: Message) -> None:
    await message.answer(
        "Я не понял сообщение.\n\nНажми кнопку снизу или используй /start",
        reply_markup=main_menu(),
    )


async def main() -> None:
    global mail_loop_task

    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    mail_loop_task = asyncio.create_task(check_new_messages_loop())
    try:
        await dp.start_polling(bot)
    finally:
        if mail_loop_task:
            mail_loop_task.cancel()
            try:
                await mail_loop_task
            except asyncio.CancelledError:
                pass
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
