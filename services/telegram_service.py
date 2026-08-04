import logging

import telebot

from config.settings import BOT_TOKEN
from handlers.command_handler import register_command_handlers
from handlers.message_handler import register_message_handlers


def init_bot() -> telebot.TeleBot:
    bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None, threaded=True, num_threads=4)

    bot.delete_webhook(drop_pending_updates=True)
    logging.info("Webhook removed, starting polling mode")

    register_command_handlers(bot)
    register_message_handlers(bot)

    logging.info("Bot initialized, all handlers registered")
    return bot
