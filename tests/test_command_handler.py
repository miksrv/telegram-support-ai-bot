import os
from unittest.mock import MagicMock

import pytest

from database import bot_state_repo, context_repo
from database.db import close_db, init_db
from handlers.command_handler import _command_arg, register_command_handlers


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    db_path = os.path.join(tmp_path, "test_support_bot.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    init_db()
    yield
    close_db()


class _FakeBot:
    """Stands in for telebot.TeleBot — captures decorated handlers by command name."""

    def __init__(self):
        self.handlers = {}
        self.sent = []

    def message_handler(self, commands=None, **kwargs):  # noqa: ARG002
        def decorator(func):
            for command in commands or []:
                self.handlers[command] = func
            return func

        return decorator

    def send_message(self, chat_id, text, **kwargs):  # noqa: ARG002
        self.sent.append((chat_id, text))

    def reply_to(self, message, text, **kwargs):  # noqa: ARG002
        self.sent.append((message.chat.id, text))


def _message(text, user_id=123456789, chat_id=1):  # conftest sets ADMIN_IDS=123456789
    message = MagicMock()
    message.chat = MagicMock(id=chat_id, title="Test Chat")
    message.from_user = MagicMock(id=user_id)
    message.text = text
    return message


def test_pause_sets_the_global_flag_and_replies():
    bot = _FakeBot()
    register_command_handlers(bot)

    assert bot_state_repo.is_paused() is False
    bot.handlers["pause"](_message("/pause"))

    assert bot_state_repo.is_paused() is True
    assert "приостановлен" in bot.sent[-1][1]


def test_resume_clears_the_global_flag_and_replies():
    bot = _FakeBot()
    register_command_handlers(bot)

    bot_state_repo.set_paused(True, updated_by=123456789)
    bot.handlers["resume"](_message("/resume"))

    assert bot_state_repo.is_paused() is False
    assert "активен" in bot.sent[-1][1]


def test_status_reports_paused_state():
    bot = _FakeBot()
    register_command_handlers(bot)

    bot.handlers["status"](_message("/status"))
    assert "Бот активен" in bot.sent[-1][1]

    bot_state_repo.set_paused(True, updated_by=123456789)
    bot.handlers["status"](_message("/status"))
    assert "на паузе" in bot.sent[-1][1]


def test_pause_and_resume_are_ignored_for_non_admins():
    bot = _FakeBot()
    register_command_handlers(bot)

    bot.handlers["pause"](_message("/pause", user_id=999))

    assert bot_state_repo.is_paused() is False
    assert bot.sent == []


# --------------------------------------------------
# _command_arg — must ignore a "@botusername" suffix, not treat it as the
# argument (see the /context@look_at_stars_bot bug report).
# --------------------------------------------------


def test_command_arg_strips_bot_username_suffix_with_no_real_argument():
    assert _command_arg("/context@look_at_stars_bot") == ""
    assert _command_arg("/event@look_at_stars_bot") == ""


def test_command_arg_extracts_real_argument_after_bot_username_suffix():
    assert _command_arg("/context@look_at_stars_bot Новый текст контекста") == "Новый текст контекста"


def test_command_arg_extracts_real_argument_without_bot_username_suffix():
    assert _command_arg("/context Новый текст контекста") == "Новый текст контекста"


def test_command_arg_empty_for_bare_command():
    assert _command_arg("/context") == ""


def test_context_with_bot_username_suffix_and_no_text_shows_current_context_instead_of_overwriting():
    """
    Regression test: "/context@look_at_stars_bot" with no real argument must
    behave exactly like bare "/context" — show the current context — not
    silently overwrite it with "@look_at_stars_bot".
    """
    bot = _FakeBot()
    register_command_handlers(bot)

    context_repo.set_project_context("Настоящий контекст проекта", updated_by=123456789)
    bot.handlers["context"](_message("/context@look_at_stars_bot"))

    assert context_repo.get_project_context() == "Настоящий контекст проекта"  # unchanged
    assert "@look_at_stars_bot" not in bot.sent[-1][1]
    assert "Настоящий контекст проекта" in bot.sent[-1][1]


def test_event_with_bot_username_suffix_and_no_text_shows_current_context_instead_of_overwriting():
    bot = _FakeBot()
    register_command_handlers(bot)

    context_repo.set_trip_context("Настоящий контекст выезда", updated_by=123456789)
    bot.handlers["event"](_message("/event@look_at_stars_bot"))

    assert context_repo.get_trip_context() == "Настоящий контекст выезда"  # unchanged
    assert "@look_at_stars_bot" not in bot.sent[-1][1]
    assert "Настоящий контекст выезда" in bot.sent[-1][1]


def test_context_with_bot_username_suffix_and_real_text_sets_the_intended_value():
    bot = _FakeBot()
    register_command_handlers(bot)

    bot.handlers["context"](_message("/context@look_at_stars_bot Новый контекст"))

    assert context_repo.get_project_context() == "Новый контекст"
