"""
Admin-only commands — see CLAUDE.md's "Admin commands" for scope rules:
/enable and /disable must run inside the target chat; the rest are global
(recommended to run in a DM with the bot to avoid dumping long context text
into a group).
"""

import html

import telebot
from telebot.types import Message

from database.chats_repo import list_chats, set_active
from database.context_repo import get_project_context, get_trip_context, set_project_context, set_trip_context
from database.messages_repo import count_answered_by_chat, count_messages
from database.users_repo import count_users
from utils.admin import admin_only

_HELP_TEXT = (
    "🤖 <b>Бот-помощник по астровыездам</b>\n\n"
    "<b>В этом чате:</b>\n"
    "  /enable — включить бота в этом чате\n"
    "  /disable — выключить бота в этом чате\n\n"
    "<b>Глобальные команды (лучше в личку боту):</b>\n"
    "  /event — показать текущий контекст выезда\n"
    "  /event &lt;текст&gt; — задать контекст текущего выезда\n"
    "  /context — показать общий контекст проекта\n"
    "  /context &lt;текст&gt; — задать общий контекст проекта\n"
    "  /status — активные чаты и текущий выезд\n"
    "  /stats — статистика по вопросам и пользователям"
)


def register_command_handlers(bot: telebot.TeleBot) -> None:

    @bot.message_handler(commands=["start", "help"])
    @admin_only
    def cmd_help(message: Message) -> None:
        bot.send_message(message.chat.id, _HELP_TEXT, parse_mode="HTML")

    @bot.message_handler(commands=["enable"])
    @admin_only
    def cmd_enable(message: Message) -> None:
        set_active(message.chat.id, message.chat.title or str(message.chat.id), True)
        bot.reply_to(message, "✅ Бот включён в этом чате.")

    @bot.message_handler(commands=["disable"])
    @admin_only
    def cmd_disable(message: Message) -> None:
        set_active(message.chat.id, message.chat.title or str(message.chat.id), False)
        bot.reply_to(message, "🔴 Бот выключен в этом чате.")

    @bot.message_handler(commands=["event"])
    @admin_only
    def cmd_event(message: Message) -> None:
        arg = message.text[len("/event") :].strip()

        if not arg:
            current = get_trip_context()
            text = (
                f"<b>Текущий контекст выезда:</b>\n\n{html.escape(current)}"
                if current
                else "Контекст выезда не задан.\n\nИспользуй /event &lt;текст&gt; для установки."
            )
            bot.send_message(message.chat.id, text, parse_mode="HTML")
            return

        set_trip_context(arg, message.from_user.id)
        bot.send_message(message.chat.id, "✅ Контекст выезда обновлён.")

    @bot.message_handler(commands=["context"])
    @admin_only
    def cmd_context(message: Message) -> None:
        arg = message.text[len("/context") :].strip()

        if not arg:
            current = get_project_context()
            text = (
                f"<b>Текущий общий контекст проекта:</b>\n\n{html.escape(current)}"
                if current
                else "Общий контекст не задан.\n\nИспользуй /context &lt;текст&gt; для установки."
            )
            bot.send_message(message.chat.id, text, parse_mode="HTML")
            return

        set_project_context(arg, message.from_user.id)
        bot.send_message(message.chat.id, "✅ Общий контекст проекта обновлён.")

    @bot.message_handler(commands=["status"])
    @admin_only
    def cmd_status(message: Message) -> None:
        chats = list_chats()
        lines = ["<b>Чаты:</b>"]
        if not chats:
            lines.append("нет ни одного известного чата")
        for chat in chats:
            state = "🟢 включён" if chat["active"] else "🔴 выключен"
            lines.append(f"  {html.escape(chat['title'] or str(chat['chat_id']))} — {state}")

        trip = get_trip_context()
        lines.append("\n<b>Текущий выезд:</b>")
        lines.append(html.escape(trip) if trip else "не задан")

        bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML")

    @bot.message_handler(commands=["stats"])
    @admin_only
    def cmd_stats(message: Message) -> None:
        answered = count_messages(relevant_only=True)
        total = count_messages()
        users = count_users()
        by_chat = count_answered_by_chat()

        lines = [
            "<b>Статистика:</b>",
            f"  Всего сообщений: {total}",
            f"  Отвечено вопросов: {answered}",
            f"  Пользователей: {users}",
        ]

        if by_chat:
            chats_by_id = {c["chat_id"]: c["title"] for c in list_chats()}
            lines.append("\n<b>По чатам:</b>")
            for row in by_chat:
                title = chats_by_id.get(row["chat_id"]) or str(row["chat_id"])
                lines.append(f"  {html.escape(title)}: {row['answered']}")

        bot.send_message(message.chat.id, "\n".join(lines), parse_mode="HTML")
