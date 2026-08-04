import logging
import os
from unittest.mock import MagicMock

from config.settings import ORGANIZERS_CHAT_ID
from database.db import close_db, init_db
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

    def reply_to(self, message, text, **kwargs):  # noqa: ARG002
        pass


def _message(chat_id, user_id=1, text="hello"):
    message = MagicMock()
    message.chat = MagicMock(id=chat_id)
    message.from_user = MagicMock(id=user_id, username="tester", first_name="Test", last_name="")
    message.text = text
    message.message_id = 1
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

    monkeypatch.setattr("handlers.message_handler.is_paused", lambda: False)
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

    monkeypatch.setattr("handlers.message_handler.is_paused", lambda: False)
    reached_is_active = {"called": False}
    monkeypatch.setattr(
        "handlers.message_handler.is_active",
        lambda chat_id: reached_is_active.update(called=True) or False,
    )

    bot.handler(_message(ORGANIZERS_CHAT_ID - 1))  # any other chat

    assert reached_is_active["called"] is True


def test_paused_bot_skips_everything_before_the_organizers_chat_check(monkeypatch):
    """
    /pause is a global kill switch — it must short-circuit before the
    organizers-chat check and is_active(), for every chat, so a paused bot
    never touches the DB or spends an LLM call anywhere.
    """
    bot = _FakeBot()
    register_message_handlers(bot)

    monkeypatch.setattr("handlers.message_handler.is_paused", lambda: True)
    reached_is_active = {"called": False}
    monkeypatch.setattr(
        "handlers.message_handler.is_active",
        lambda chat_id: reached_is_active.update(called=True) or True,
    )

    bot.handler(_message(ORGANIZERS_CHAT_ID - 1))  # an ordinary, non-organizers chat

    assert reached_is_active["called"] is False


def test_llm_verdict_is_logged_at_debug_level(monkeypatch, caplog, tmp_path):
    """
    The relevant/reply verdict from classify_and_reply is logged at DEBUG
    right after the call, so a live deployment's debug log shows what the
    LLM actually decided for a message — not just that an update arrived.
    """
    db_path = os.path.join(tmp_path, "test_support_bot.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    init_db()

    bot = _FakeBot()
    register_message_handlers(bot)

    monkeypatch.setattr("handlers.message_handler.is_paused", lambda: False)
    monkeypatch.setattr("handlers.message_handler.is_active", lambda chat_id: True)
    monkeypatch.setattr(
        "handlers.message_handler.classify_and_reply",
        lambda *args, **kwargs: {"relevant": True, "reply": "тестовый ответ"},
    )
    monkeypatch.setattr("handlers.message_handler.forward_qa", lambda *args, **kwargs: None)

    caplog.set_level(logging.DEBUG)
    bot.handler(_message(ORGANIZERS_CHAT_ID - 1, user_id=42, text="Вопрос?"))

    verdict_logs = [r.getMessage() for r in caplog.records if "LLM verdict" in r.getMessage()]
    assert len(verdict_logs) == 1
    assert "relevant=True" in verdict_logs[0]
    assert "тестовый ответ" in verdict_logs[0]

    close_db()
