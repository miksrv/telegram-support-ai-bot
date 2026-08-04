from unittest.mock import MagicMock

from services.forward_service import _message_link, forward_qa


def _message(chat_id, username=None, title="Astro Chat", message_id=42, text="Когда выезд?"):
    message = MagicMock()
    message.chat = MagicMock(id=chat_id, username=username, title=title)
    message.message_id = message_id
    message.text = text
    return message


def test_message_link_uses_public_username_when_available():
    message = _message(chat_id=-100123, username="astro_chat")
    assert _message_link(message) == "https://t.me/astro_chat/42"


def test_message_link_falls_back_to_internal_c_link_for_private_supergroup():
    message = _message(chat_id=-1001234567890, username=None)
    assert _message_link(message) == "https://t.me/c/1234567890/42"


def test_forward_qa_sends_formatted_card_to_organizers_chat():
    from config.settings import ORGANIZERS_CHAT_ID

    bot = MagicMock()
    message = _message(chat_id=-1001234567890, username=None)
    identity = {"first_name": "Ann", "last_name": "", "profile_link": "https://t.me/asker"}

    forward_qa(bot, message, identity, "16 августа")

    bot.send_message.assert_called_once()
    args, kwargs = bot.send_message.call_args
    assert args[0] == ORGANIZERS_CHAT_ID
    assert "16 августа" in args[1]
    assert "Когда выезд?" in args[1]
    assert kwargs["parse_mode"] == "HTML"


def test_forward_qa_swallows_send_errors():
    bot = MagicMock()
    bot.send_message.side_effect = RuntimeError("network down")
    message = _message(chat_id=-100999, username="chat")
    identity = {"first_name": "Ann", "last_name": "", "profile_link": "https://t.me/asker"}

    forward_qa(bot, message, identity, "answer")  # must not raise
