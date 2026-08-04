"""
Main per-message triage flow — see CLAUDE.md's "Conversational message" for
the full step-by-step spec.
"""

import logging

import telebot
from telebot.types import Message

from config.settings import ORGANIZERS_CHAT_ID, USER_HISTORY_LIMIT
from core.brain import classify_and_reply
from database.chats_repo import is_active
from database.context_repo import get_project_context, get_trip_context
from database.messages_repo import get_user_history, save_message
from database.users_repo import upsert_user
from services.forward_service import forward_qa
from utils.identity import extract_telegram_identity

# Cached lazily on first use instead of at import time, since bot.get_me()
# needs a live connection to Telegram.
_bot_id_cache: dict = {}


def _get_bot_id(bot: telebot.TeleBot) -> int:
    if "id" not in _bot_id_cache:
        _bot_id_cache["id"] = bot.get_me().id
    return _bot_id_cache["id"]


def register_message_handlers(bot: telebot.TeleBot) -> None:

    @bot.message_handler(content_types=["text"])
    def handle_message(message: Message) -> None:
        # The organizers chat is a destination (forwarded Q&A cards) and a
        # place to run admin commands (handled separately by
        # command_handler.py, unaffected by this early return) — it's never a
        # community chat to triage, so its ordinary chatter is neither read
        # nor logged here.
        if message.chat.id == ORGANIZERS_CHAT_ID:
            return

        logging.debug(
            "Update received: chat_id=%s user_id=%s text=%r",
            message.chat.id,
            message.from_user.id,
            message.text,
        )
        if not is_active(message.chat.id):
            return
        if message.from_user.id == _get_bot_id(bot):
            return
        if not message.text or message.text.startswith("/"):
            return

        is_reply_to_bot = (
            message.reply_to_message is not None
            and message.reply_to_message.from_user is not None
            and message.reply_to_message.from_user.id == _get_bot_id(bot)
        )

        identity = extract_telegram_identity(message)
        upsert_user(identity)

        history = get_user_history(identity["id"], USER_HISTORY_LIMIT)
        project_context = get_project_context()
        trip_context = get_trip_context()

        verdict = classify_and_reply(message.text, project_context, trip_context, history, is_reply_to_bot)

        save_message(
            chat_id=message.chat.id,
            user_id=identity["id"],
            message_id=message.message_id,
            text=message.text,
            is_reply_to_bot=is_reply_to_bot,
            relevant=verdict["relevant"],
            reply_text=verdict["reply"],
        )

        if verdict["relevant"] and verdict["reply"]:
            try:
                bot.reply_to(message, verdict["reply"])
            except Exception as e:  # pylint: disable=broad-except
                logging.error("Failed to send reply in chat %d: %s", message.chat.id, e)
                return

            forward_qa(bot, message, identity, verdict["reply"])
