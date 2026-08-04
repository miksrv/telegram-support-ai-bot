from unittest.mock import MagicMock

from utils.admin import admin_only


def _message_from(user_id):
    message = MagicMock()
    message.from_user = MagicMock(id=user_id)
    return message


def test_admin_only_calls_through_for_admin():
    called = {}

    @admin_only
    def handler(message):
        called["ran"] = True

    # conftest sets ADMIN_IDS=123456789
    handler(_message_from(123456789))
    assert called.get("ran") is True


def test_admin_only_silently_ignores_non_admin():
    called = {}

    @admin_only
    def handler(message):
        called["ran"] = True

    handler(_message_from(999))
    assert "ran" not in called
