"""
@admin_only — gates a command handler to Telegram user IDs listed in
ADMIN_IDS, silently ignoring everyone else (per CLAUDE.md's admin command spec).
"""

import functools
import logging

from telebot.types import Message

from config.settings import ADMIN_IDS


def admin_only(func):
    @functools.wraps(func)
    def wrapper(message: Message, *args, **kwargs):
        if message.from_user.id not in ADMIN_IDS:
            # Silent to the user by design (see module docstring) — logged at
            # DEBUG so a misconfigured ADMIN_IDS is diagnosable from the logs.
            logging.debug(
                "Ignoring /%s from non-admin user_id=%s (ADMIN_IDS=%s)",
                message.text.split()[0].lstrip("/") if message.text else "?",
                message.from_user.id,
                sorted(ADMIN_IDS),
            )
            return None
        return func(message, *args, **kwargs)

    return wrapper
