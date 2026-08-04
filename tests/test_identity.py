from unittest.mock import MagicMock

from utils.identity import extract_telegram_identity


def _message_with_user(**user_kwargs):
    message = MagicMock()
    message.from_user = MagicMock(**user_kwargs)
    return message


def test_extract_identity_prefers_username_link():
    message = _message_with_user(id=1, username="asker", first_name="Ann", last_name="Ivanova")
    identity = extract_telegram_identity(message)

    assert identity == {
        "id": 1,
        "username": "asker",
        "first_name": "Ann",
        "last_name": "Ivanova",
        "profile_link": "https://t.me/asker",
    }


def test_extract_identity_falls_back_to_deep_link_without_username():
    message = _message_with_user(id=2, username=None, first_name="Ann", last_name=None)
    identity = extract_telegram_identity(message)

    assert identity["profile_link"] == "tg://user?id=2"
    assert identity["username"] == ""
    assert identity["last_name"] == ""
