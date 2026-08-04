import os
import sys
from unittest.mock import MagicMock

# Must be set before any project module is imported — config/settings.py
# validates required env vars and the active LLM_ENGINE's API key at import
# time. In CI these are also set at the job level in the workflow.
os.environ.setdefault("BOT_TOKEN", "fake_bot_token_for_testing")
os.environ.setdefault("ADMIN_IDS", "123456789")
os.environ.setdefault("ORGANIZERS_CHAT_ID", "-1001234567890")
os.environ.setdefault("LLM_ENGINE", "openai")
os.environ.setdefault("OPENAI_API_KEY", "fake_openai_key")
os.environ.setdefault("GROQ_API_KEY", "fake_groq_key")

# Stub out telebot if the package is not installed (e.g. running tests without
# the full venv). In CI requirements.txt is installed so the real package is used.
if "telebot" not in sys.modules:
    try:
        import telebot  # noqa: F401
    except ImportError:
        _telebot_stub = MagicMock()
        sys.modules["telebot"] = _telebot_stub
        sys.modules["telebot.types"] = _telebot_stub.types
