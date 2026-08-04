import logging

import telebot
from telebot import types

from config.settings import ADMIN_IDS, BOT_TOKEN, ORGANIZERS_CHAT_ID
from handlers.command_handler import register_command_handlers
from handlers.message_handler import register_message_handlers

# The Telegram "/" command-menu suggestion list is scoped per chat via
# setMyCommands(scope=...) — a UI convenience only, NOT a permission check;
# utils/admin.py's @admin_only still gates every command regardless of what
# the menu shows here. Ordinary community group chats get an empty menu (no
# hints at all — every member would see them otherwise, including /pause and
# /stats, which has no upside for a random participant); the full admin
# command set is scoped only to each admin's own DM with the bot and to the
# organizers chat, where the global/cross-chat commands actually belong.
_ADMIN_COMMANDS = [
    types.BotCommand("help", "Список команд"),
    types.BotCommand("enable", "Включить бота в этом чате"),
    types.BotCommand("disable", "Выключить бота в этом чате"),
    types.BotCommand("pause", "Приостановить бота во всех чатах"),
    types.BotCommand("resume", "Снять паузу со всех чатов"),
    types.BotCommand("event", "Показать/задать контекст текущего мероприятия"),
    types.BotCommand("context", "Показать/задать общий контекст"),
    types.BotCommand("status", "Статус бота и чатов"),
    types.BotCommand("stats", "Статистика по вопросам и пользователям"),
]


def _register_bot_commands(bot: telebot.TeleBot) -> None:
    bot.set_my_commands([], scope=types.BotCommandScopeDefault())
    bot.set_my_commands(_ADMIN_COMMANDS, scope=types.BotCommandScopeChat(chat_id=ORGANIZERS_CHAT_ID))

    for admin_id in ADMIN_IDS:
        try:
            bot.set_my_commands(_ADMIN_COMMANDS, scope=types.BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:  # pylint: disable=broad-except
            # Telegram requires the target chat to already exist from its side
            # — an admin who has never opened a DM with the bot yet has no
            # such chat, so this fails until they send it a first message.
            # Not fatal: the default-scope list still works for them meanwhile.
            logging.warning("Could not set admin command menu for admin_id=%s: %s", admin_id, e)

    logging.info("Bot command menus registered (default + organizers chat + %d admin DMs)", len(ADMIN_IDS))


def init_bot() -> telebot.TeleBot:
    bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None, threaded=True, num_threads=4)

    bot.delete_webhook(drop_pending_updates=True)
    logging.info("Webhook removed, starting polling mode")

    register_command_handlers(bot)
    register_message_handlers(bot)
    _register_bot_commands(bot)

    logging.info("Bot initialized, all handlers registered")
    return bot
