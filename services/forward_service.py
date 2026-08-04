"""
Formats and sends the answered-question "card" to the organizers' chat — see
CLAUDE.md's "Forwarding to the organizers' chat". Uses a plain formatted
send_message (not bot.forward_message) because groups with "restrict saving
content" enabled block forwards outright — a link + quoted text works
regardless of that setting.
"""

import html
import logging

import telebot
from telebot.types import Message

from config.settings import ORGANIZERS_CHAT_ID


def _message_link(message: Message) -> str:
    chat = message.chat
    if chat.username:
        return f"https://t.me/{chat.username}/{message.message_id}"

    # Private supergroups use the -100<internal_id> form for chat.id; the
    # t.me/c/ deep link needs just the internal id without that prefix.
    internal_id = str(chat.id).removeprefix("-100")
    return f"https://t.me/c/{internal_id}/{message.message_id}"


def forward_qa(bot: telebot.TeleBot, message: Message, identity: dict, answer: str) -> None:
    link = _message_link(message)
    profile_link = identity["profile_link"]
    name = html.escape(f"{identity['first_name']} {identity['last_name']}".strip() or "Без имени")
    chat_title = html.escape(message.chat.title or "")

    text = (
        f"💬 <b>Вопрос в чате «{chat_title}»</b>\n"
        f'<a href="{link}">Перейти к сообщению</a>\n\n'
        f'<b>Автор:</b> <a href="{profile_link}">{name}</a>\n\n'
        f"<b>Вопрос:</b>\n{html.escape(message.text)}\n\n"
        f"<b>Ответ бота:</b>\n{html.escape(answer)}"
    )

    try:
        bot.send_message(ORGANIZERS_CHAT_ID, text, parse_mode="HTML")
    except Exception as e:  # pylint: disable=broad-except
        logging.error("Failed to forward Q&A to organizers chat: %s", e)
