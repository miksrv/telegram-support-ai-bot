from unittest.mock import MagicMock

from config.settings import ORGANIZERS_CHAT_ID
from handlers.message_handler import register_message_handlers


class _FakeBot:
    """Stands in for telebot.TeleBot — captures the decorated handler function."""

    def __init__(self):
        self.handler = None

    def message_handler(self, *args, **kwargs):
        def decorator(func):
            self.handler = func
            return func

        return decorator

    def get_me(self):
        return MagicMock(id=999)


def _message(chat_id, user_id=1, text="hello"):
    message = MagicMock()
    message.chat = MagicMock(id=chat_id)
    message.from_user = MagicMock(id=user_id)
    message.text = text
    message.reply_to_message = None
    return message


def test_organizers_chat_messages_are_never_read_or_processed(monkeypatch):
    """
    The organizers chat is a destination (forwarded Q&A cards) and a place to
    run admin commands (handled separately by command_handler.py) — its
    ordinary chatter must never reach is_active()/the LLM/the DB.
    """
    bot = _FakeBot()
    register_message_handlers(bot)

    reached_is_active = {"called": False}
    monkeypatch.setattr(
        "handlers.message_handler.is_active",
        lambda chat_id: reached_is_active.update(called=True) or True,
    )

    bot.handler(_message(ORGANIZERS_CHAT_ID))

    assert reached_is_active["called"] is False


def test_non_organizers_chat_messages_still_reach_is_active(monkeypatch):
    bot = _FakeBot()
    register_message_handlers(bot)

    reached_is_active = {"called": False}
    monkeypatch.setattr(
        "handlers.message_handler.is_active",
        lambda chat_id: reached_is_active.update(called=True) or False,
    )

    bot.handler(_message(ORGANIZERS_CHAT_ID - 1))  # any other chat

    assert reached_is_active["called"] is True
