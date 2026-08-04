"""
CASE — Telegram Support AI Bot
Reads every message in chats it's turned on in, asks an LLM whether it's a
question about the current astro-trip, and answers/forwards it if so.
"""

import logging
import os
import signal
import sys
import time

from dotenv import load_dotenv

load_dotenv()

_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="[%(levelname)s] %(name)s: %(message)s",
)

# urllib3's request-level debug logging includes the full request URL — which
# for both the Telegram Bot API and the LLM providers means the bot token /
# API key would end up in plaintext logs under LOG_LEVEL=DEBUG. Keep it quiet
# regardless of our own log level; nothing in this app relies on its output.
logging.getLogger("urllib3").setLevel(logging.WARNING)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db import close_db, init_db  # noqa: E402
from services.telegram_service import init_bot  # noqa: E402

_ALLOWED_UPDATES = ["message"]


def _shutdown(signum, frame):  # pylint: disable=unused-argument
    logging.info("Shutting down...")
    close_db()
    sys.exit(0)


signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


if __name__ == "__main__":
    logging.info("CASE starting...")
    init_db()
    bot = init_bot()

    while True:
        try:
            bot.infinity_polling(
                timeout=60,
                long_polling_timeout=60,
                allowed_updates=_ALLOWED_UPDATES,
            )
        except Exception as e:  # pylint: disable=broad-except
            logging.critical("Polling crashed: %s", e)
            time.sleep(10)
