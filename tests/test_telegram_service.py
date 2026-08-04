from unittest.mock import MagicMock

from config.settings import ADMIN_IDS, ORGANIZERS_CHAT_ID
from services.telegram_service import _register_bot_commands


def test_registers_default_organizers_and_per_admin_command_scopes():
    bot = MagicMock()

    _register_bot_commands(bot)

    calls = bot.set_my_commands.call_args_list
    chat_ids = {kwargs["scope"].chat_id for _, kwargs in calls}

    # Ordinary chats (default scope, chat_id=None) get an empty menu — no
    # hints for random community-chat members.
    default_calls = [args for args, kwargs in calls if kwargs["scope"].chat_id is None]
    assert len(default_calls) == 1
    assert default_calls[0][0] == []

    # The full admin command set goes only to the organizers chat and every
    # configured admin's own DM.
    assert ORGANIZERS_CHAT_ID in chat_ids
    assert ADMIN_IDS <= chat_ids


def test_a_failed_admin_dm_scope_does_not_block_the_others():
    bot = MagicMock()
    total_calls = 2 + len(ADMIN_IDS)  # default scope + organizers chat + one call per admin
    # Every call succeeds except the last admin's DM, which raises — must not abort the loop.
    bot.set_my_commands.side_effect = [None] * (total_calls - 1) + [Exception("chat not found")]

    _register_bot_commands(bot)  # must not raise

    assert bot.set_my_commands.call_count == total_calls
