import os

import pytest

from database import chats_repo, context_repo, messages_repo, users_repo
from database.db import close_db, get_db, init_db


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    db_path = os.path.join(tmp_path, "test_support_bot.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    init_db()
    yield
    close_db()


def _identity(user_id=111, username="tester"):
    return {
        "id": user_id,
        "username": username,
        "first_name": "Test",
        "last_name": "User",
        "profile_link": f"https://t.me/{username}",
    }


def test_upsert_user_creates_and_updates():
    users_repo.upsert_user(_identity())
    user = users_repo.get_user(111)
    assert user["username"] == "tester"
    assert user["questions_count"] == 0

    users_repo.upsert_user(_identity(username="renamed"))
    user = users_repo.get_user(111)
    assert user["username"] == "renamed"
    assert users_repo.count_users() == 1


def test_save_message_increments_questions_count_only_when_relevant():
    users_repo.upsert_user(_identity())

    messages_repo.save_message(
        chat_id=1, user_id=111, message_id=1, text="Привет", is_reply_to_bot=False, relevant=False, reply_text=""
    )
    assert users_repo.get_user(111)["questions_count"] == 0

    messages_repo.save_message(
        chat_id=1,
        user_id=111,
        message_id=2,
        text="Когда выезд?",
        is_reply_to_bot=False,
        relevant=True,
        reply_text="16 августа",
    )
    assert users_repo.get_user(111)["questions_count"] == 1
    assert messages_repo.count_messages() == 2
    assert messages_repo.count_messages(relevant_only=True) == 1


def test_get_user_history_returns_only_relevant_oldest_first():
    users_repo.upsert_user(_identity())
    messages_repo.save_message(
        chat_id=1, user_id=111, message_id=1, text="Q1", is_reply_to_bot=False, relevant=True, reply_text="A1"
    )
    messages_repo.save_message(
        chat_id=1, user_id=111, message_id=2, text="off-topic", is_reply_to_bot=False, relevant=False, reply_text=""
    )
    messages_repo.save_message(
        chat_id=2, user_id=111, message_id=3, text="Q2", is_reply_to_bot=False, relevant=True, reply_text="A2"
    )

    history = messages_repo.get_user_history(111, limit=5)
    assert [row["text"] for row in history] == ["Q1", "Q2"]


def test_get_user_history_respects_limit():
    users_repo.upsert_user(_identity())
    for i in range(3):
        messages_repo.save_message(
            chat_id=1, user_id=111, message_id=i, text=f"Q{i}", is_reply_to_bot=False, relevant=True, reply_text="A"
        )

    history = messages_repo.get_user_history(111, limit=2)
    assert len(history) == 2
    assert [row["text"] for row in history] == ["Q1", "Q2"]


def test_chats_repo_set_and_check_active():
    assert chats_repo.is_active(42) is False

    chats_repo.set_active(42, "Test Chat", True)
    assert chats_repo.is_active(42) is True

    chats_repo.set_active(42, "Test Chat", False)
    assert chats_repo.is_active(42) is False

    chats = chats_repo.list_chats()
    assert len(chats) == 1
    assert chats[0]["title"] == "Test Chat"


def test_context_repo_project_and_trip_are_independent():
    from database.seed_data import DEFAULT_PROJECT_CONTEXT

    assert context_repo.get_project_context() == DEFAULT_PROJECT_CONTEXT  # seeded by init_db()
    assert context_repo.get_trip_context() == ""

    context_repo.set_project_context("Общая инфа", updated_by=1)
    context_repo.set_trip_context("Выезд 16 августа", updated_by=1)

    assert context_repo.get_project_context() == "Общая инфа"
    assert context_repo.get_trip_context() == "Выезд 16 августа"

    context_repo.set_trip_context("Выезд 30 августа", updated_by=2)
    assert context_repo.get_trip_context() == "Выезд 30 августа"
    assert context_repo.get_project_context() == "Общая инфа"  # untouched


def test_init_db_seeds_default_project_context_without_clobbering_edits():
    """
    The default project_context text is a convenience seed for a brand-new
    DB, not a value init_db() should keep re-asserting — an admin's /context
    edit must survive a container restart (init_db() runs again on boot).
    """
    context_repo.set_project_context("Кастомный контекст админа", updated_by=1)
    init_db()  # simulates a restart

    assert context_repo.get_project_context() == "Кастомный контекст админа"


def test_get_db_reuses_the_same_connection_per_thread():
    assert get_db() is get_db()


def test_close_db_survives_a_connection_opened_by_another_thread():
    """
    telebot runs handlers on worker threads (see get_db()'s docstring), but
    close_db() runs from the main-thread signal handler on shutdown. sqlite3
    forbids closing a connection from any thread other than the one that
    opened it — close_db() must swallow that instead of crashing the
    shutdown path (see database/db.py).
    """
    import threading

    from database import db as db_module

    get_db()  # main-thread connection

    def open_in_worker_thread():
        get_db()

    t = threading.Thread(target=open_in_worker_thread)
    t.start()
    t.join()

    assert len(db_module._all_conns) == 2  # main-thread + worker-thread connections
    close_db()  # must not raise sqlite3.ProgrammingError
