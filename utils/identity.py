"""
Telegram Identity Utilities
Extracts a Telegram user's identity from a message — the exact dict shape
database/users_repo.py::upsert_user expects.
"""

from telebot.types import Message


def extract_telegram_identity(message: Message) -> dict:
    """
    Returns a dictionary with:
    - id: Telegram user ID
    - username
    - first_name
    - last_name
    - profile_link: https://t.me/<username> if the user has one, otherwise
      the always-available tg://user?id=<id> deep link
    """
    user = message.from_user

    profile_link = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"

    return {
        "id": user.id,
        "username": user.username or "",
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "profile_link": profile_link,
    }
