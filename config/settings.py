import os

from dotenv import load_dotenv

load_dotenv()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name!r} is not set")
    return value


BOT_TOKEN = require_env("BOT_TOKEN")
ADMIN_IDS = {int(x) for x in require_env("ADMIN_IDS").split(",") if x.strip()}
ORGANIZERS_CHAT_ID = int(require_env("ORGANIZERS_CHAT_ID"))

# --------------------------------------------------
# LLM Engine
# --------------------------------------------------
# Selects which cloud LLM core/llm powers the bot with. Only the API key for
# the active engine is required; the other provider's key may be left blank —
# but if both are filled in, the inactive one is kept on standby and the bot
# automatically fails over to it when the active engine runs out of quota
# (see core/llm/engine.py). Defaults to "openai" per this bot's spec — Groq is
# the cost-effective fallback, not the primary.
# Add a new provider by adding a file under core/llm/ implementing
# LLMProvider and registering it in core/llm/engine.py's _PROVIDERS dict.

LLM_ENGINE = os.getenv("LLM_ENGINE", "openai").strip().lower()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

if LLM_ENGINE not in ("openai", "groq"):
    raise RuntimeError(f"Unknown LLM_ENGINE '{LLM_ENGINE}', expected 'openai' or 'groq'")
if LLM_ENGINE == "openai" and not OPENAI_API_KEY:
    raise RuntimeError("LLM_ENGINE=openai requires OPENAI_API_KEY to be set")
if LLM_ENGINE == "groq" and not GROQ_API_KEY:
    raise RuntimeError("LLM_ENGINE=groq requires GROQ_API_KEY to be set")

# Deliberately cheap models — see the "Cost/latency note" in CLAUDE.md: one
# LLM call runs per chat message in every active chat, not just triggered ones.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Past Q&A rows per user injected into the prompt as conversational context.
USER_HISTORY_LIMIT = int(os.getenv("USER_HISTORY_LIMIT", "5"))

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "support_bot.db")
