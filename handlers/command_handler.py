"""
Admin-only commands — see CLAUDE.md's "Admin commands" for scope rules:
/enable and /disable must run inside the target chat; the rest are global
(recommended to run in a DM with the bot to avoid dumping long context text
into a group).
"""

import html

import telebot
from telebot.types import Message

from database.bot_state_repo import is_paused, set_paused
from database.chats_repo import list_chats, set_active
from database.context_repo import get_project_context, get_trip_context, set_project_context, set_trip_context
from database.messages_repo import count_answered_by_chat, count_messages
from database.users_repo import count_users
from utils.admin import admin_only


def _command_arg(text: str) -> str:
    """
    Returns everything after the command token — correctly handling the
    "@botusername" suffix Telegram appends in group chats (e.g.
    "/context@look_at_stars_bot some text", common with several bots in one
    chat). Naive prefix-stripping (text[len("/context"):]) would leave
    "@look_at_stars_bot" behind as a bogus non-empty argument, silently
    overwriting the context with garbage instead of showing the current one.
    """
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


_HELP_TEXT = (
    "🤖 <b>CASE — бот технической поддержки</b>\n"
    "Отвечает на вопросы в чате по заданному контексту — тема мероприятия/проекта не важна, "
    "всё настраивается командами ниже.\n\n"
    "<b>В этом чате:</b>\n"
    "  /enable — включить бота в этом чате\n"
    "  /disable — выключить бота в этом чате\n\n"
    "<b>Глобальные команды (лучше в личку боту):</b>\n"
    "  /pause — приостановить бота во всех чатах сразу (например, когда мероприятие закончилось)\n"
    "  /resume — снова включить после /pause\n"
    "  /event — показать текущий контекст мероприятия\n"
    "  /event &lt;текст&gt; — задать контекст текущего мероприятия\n"
    "  /context — показать общий (вечный) контекст\n"
    "  /context &lt;текст&gt; — задать общий контекст\n"
    "  /status — активные чаты, пауза и текущий контекст мероприятия\n"
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

    @bot.message_handler(commands=["pause"])
    @admin_only
    def cmd_pause(message: Message) -> None:
        set_paused(True, message.from_user.id)
        bot.send_message(
            message.chat.id,
            "⏸ Бот приостановлен во всех чатах — не будет отвечать и обращаться к LLM, пока не выполнишь /resume.",
        )

    @bot.message_handler(commands=["resume"])
    @admin_only
    def cmd_resume(message: Message) -> None:
        set_paused(False, message.from_user.id)
        bot.send_message(message.chat.id, "▶️ Бот снова активен в чатах, где он включён (/enable).")

    @bot.message_handler(commands=["event"])
    @admin_only
    def cmd_event(message: Message) -> None:
        arg = _command_arg(message.text)

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
        arg = _command_arg(message.text)

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
        lines = ["⏸ <b>Бот на паузе</b> (во всех чатах — см. /resume)" if is_paused() else "▶️ Бот активен"]

        chats = list_chats()
        lines.append("\n<b>Чаты:</b>")
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
