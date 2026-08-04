# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Related repositories

This bot is one of three Telegram bots maintained by the same author; when in doubt about a convention (module
layout, LLM engine pattern, env var naming, test setup), check these for precedent:

- [miksrv/telegram-ai-bot](https://github.com/miksrv/telegram-ai-bot) — TARS, a conversational AI bot for an
  astronomy community chat, with a pluggable Groq/OpenAI LLM engine (`core/llm/`), proactive posting, and a
  CubeSat/starmap MQTT integration. The pluggable-provider pattern in `core/llm/` here is copied from that repo.
- [miksrv/telegram-business-ai-bot](https://github.com/miksrv/telegram-business-ai-bot) — an AI auto-reply
  assistant for Telegram Business accounts, same `core/llm/` pattern, per-contact context and style learning.

## Project overview

**telegram-support-ai-bot** — Telegram bot name **CASE** — is a Telegram bot for the "Смотри на звезды"
(Stargazing) astronomy community. The
community announces stargazing trips ("астровыезды") in a Telegram channel and discusses them in several group
chats. Every time registration opens, the same logistical questions ("how do I register?", "where do we meet?",
"what do I bring?") get repeated dozens of times in each chat because people don't read the announcement or the
[event page](https://astro.miksoft.pro/stargazing).

The bot is added to those group chats and, once turned on by an organizer, reads every message. It sends each one
to OpenAI with the persistent project context and the current trip's context, asking the model to decide whether
the message is a question about the trip and, if so, draft an answer. Relevant messages get an in-chat reply and a
copy forwarded to a private organizers' chat (with a link back to the original message) so a human can step in or
follow up. Every user, question, and answer is logged to SQLite for later reuse (building a real FAQ, following up
with attendees, etc.).

The bot is named **CASE**, after the utility robot from *Interstellar* — TARS's counterpart in the same movie,
picked deliberately since `telegram-ai-bot`'s bot is named TARS. CASE is warm, unfailingly polite, and a little
playful — light humor and the occasional emoji are welcome where they fit, and it greets back when greeted — but
it stays focused: it only names itself if directly asked who/what it is (see `core/prompts.py`), and it never
turns into idle chit-chat — it only replies when there's a real, context-answerable question underneath, same as
before this tone was added. Less of a chatterbox than TARS, not personality-free.

## Language policy

- **Code, comments, docstrings, commit messages, this file, README.md** — English, no exceptions.
- **Everything the bot itself produces or exposes to Telegram users** — Russian: command help text, all chat
  replies, error/status messages, forwarded-card labels.
- **Slash-command names stay Latin/ASCII** (`/enable`, `/event`, …) — this is a Telegram Bot API constraint, not a
  style choice: BotFather only accepts `[a-z0-9_]` in command names, so a Cyrillic command is not possible. Only
  the command's *description* (shown in the `/` menu and in `/help`) is Russian.

## Architecture

```
main.py                        # Entry point: init DB, init bot, start polling
config/settings.py             # All configuration, loaded from .env
core/
  brain.py                     # Builds the classify+reply prompt, calls the LLM engine, validates the JSON response
  llm/                         # Pluggable cloud LLM engine (same pattern as the sibling repos)
    engine.py                  # LLMEngine: picks the active provider, single .complete() entry point used by brain.py
    base.py                    # LLMProvider interface + shared HTTP session/retry helper
    openai_provider.py         # OpenAIProvider(LLMProvider) — primary provider (LLM_ENGINE default)
    groq_provider.py           # GroqProvider(LLMProvider) — standby fallback, activated on OpenAI quota exhaustion
  prompts.py                   # System prompt template: persistent context + event context + user history + is_reply_to_bot
database/
  db.py                        # SQLite connection/schema init, shared across handler threads
  users_repo.py                 # Upsert/fetch user profile (id, username, name, profile link, question count)
  messages_repo.py              # Save each observed message + verdict/answer; fetch a user's recent Q&A history
  chats_repo.py                 # Per-chat active/inactive flag
  context_repo.py               # Persistent project context + current trip context (single-row tables, versioned by updated_at)
  seed_data.py                   # DEFAULT_PROJECT_CONTEXT — seeded into project_context on first init_db()
  bot_state_repo.py              # Global pause/resume flag (/pause, /resume) — overrides every chat's active flag at once
handlers/
  message_handler.py            # Main per-message flow (see "Conversational message" below)
  command_handler.py            # Admin-only commands: /enable, /disable, /pause, /resume, /event, /context, /status, /stats, /help
services/
  telegram_service.py           # Bot init, handler registration, per-chat "/" command-menu scoping
  forward_service.py            # Formats and sends the Q&A "card" to the organizers chat
utils/
  identity.py                   # Extracts a Telegram user identity dict (id, name, username, profile link) from a message
  admin.py                      # @admin_only decorator — checks message.from_user.id against ADMIN_IDS
data/                           # SQLite database file (gitignored)
```

## LLM engine

Same pluggable-provider design as the sibling repos: `core/brain.py` never calls a provider's HTTP API directly, it
calls `core/llm/engine.py`'s `llm_engine.complete(messages, *, temperature, max_tokens, json_mode=True)`. Two
providers are implemented — `OpenAIProvider` (`core/llm/openai_provider.py`) and `GroqProvider`
(`core/llm/groq_provider.py`) — behind the shared `LLMProvider` interface (`core/llm/base.py`).

`LLM_ENGINE` picks the primary provider and defaults to `"openai"` — this bot's spec calls for OpenAI as the
primary engine, unlike `telegram-ai-bot`/`telegram-business-ai-bot` where either provider can be primary. If the
*other* provider's API key is also filled in, `LLMEngine` keeps it on standby and automatically fails over to it
for the rest of the process's lifetime the moment the primary provider raises `LLMQuotaExceededError` (account out
of balance/quota — see `core/llm/base.py:is_quota_error`), then retries the call once against the fallback.
Ordinary transient errors (rate limits, connection resets) are already retried with backoff by
`post_with_retry`/`build_session` before they ever reach this fallback logic — the standby switch is specifically
for "the account ran dry," not for "one request hiccuped." The recommended setup is `LLM_ENGINE=openai` with both
`OPENAI_API_KEY` and `GROQ_API_KEY` filled in, so Groq is the cost-effective safety net if OpenAI's quota runs out
mid-event. Adding a third provider means one file implementing `LLMProvider` plus one line in `engine.py`'s
`_PROVIDERS` registry — nothing else changes.

## Key data flows

### Conversational message (the core loop)

Runs on every non-command text message in a chat marked `active` in `chats_repo`, unless the bot is globally
paused:

1. `handlers/message_handler.py` ignores the message early if: the bot is paused (`bot_state_repo.is_paused()`
   — see "Global pause switch" below), the chat is `ORGANIZERS_CHAT_ID` (its ordinary chatter is never triaged —
   only commands, handled separately by `command_handler.py`, reach it), the chat is not active, the sender is
   the bot itself, the message has no text, or the text is a command (`/...`).
2. Determine `is_reply_to_bot`: `message.reply_to_message` is set and its `from.id` equals the bot's own id.
3. `database/users_repo.py` upserts the sender's profile (id, username, display name, profile link
   `tg://user?id=<id>` or `https://t.me/<username>`, last-seen timestamp).
4. `database/messages_repo.py` fetches the sender's last `USER_HISTORY_LIMIT` (default 5) saved Q&A rows —
   across *all* chats, not just this one — so a follow-up question asked days later or in a different chat still
   has continuity, even if the user doesn't reply to the bot's earlier message.
5. `core/brain.py` builds one prompt (`core/prompts.py`) combining: the persistent project context, the current
   trip context, the sender's recent history from step 4, the message text, and the `is_reply_to_bot` flag. When
   `is_reply_to_bot` is true, the prompt instructs the model to **always** treat the message as relevant and
   produce an answer, regardless of topic — this is what satisfies "always answer replies to the bot," since a
   user who bothers to reply to the bot's message is continuing that conversation by definition.
6. One call to the LLM engine returns JSON (see "LLM response contract" below); `core/brain.py` validates it
   defensively (missing/invalid JSON is treated as `{"relevant": false, "reply": ""}` — a failure never crashes
   the handler and never fabricates a reply).
7. `database/messages_repo.py` saves the message unconditionally — text, `is_reply_to_bot`, the verdict, and the
   answer text (empty when not relevant) — this is what makes the DB useful as a growing FAQ/history dataset even
   for messages the bot didn't answer.
8. If `relevant` is true and `reply` is non-empty: `bot.reply_to()` sends the answer in the group as a genuine
   Telegram reply to the original message, then `services/forward_service.py` sends a formatted card to
   `ORGANIZERS_CHAT_ID` (see below).
9. Otherwise: no visible action. The message is already saved from step 7.

### Forwarding to the organizers' chat

`services/forward_service.py::forward_qa()` is called only for messages the bot answered (step 8 above). It sends
one message to `ORGANIZERS_CHAT_ID` containing: a link back to the original message (`https://t.me/c/<internal
chat id>/<message_id>` for private supergroups, `https://t.me/<username>/<message_id>` for public ones — resolved
from `message.chat`), the asker's profile link, the question text, and the bot's answer. It uses a formatted
`send_message`, not `bot.forward_message()`, because groups with "restrict saving content" enabled block forwards
outright — a plain link + quoted text works regardless of that setting and lets organizers jump to the message
themselves.

### Global pause switch

`database/bot_state_repo.py` holds a single `bot_state.paused` flag, set via `/pause`/`/resume` and checked first
thing in `handlers/message_handler.py` — deliberately separate from each chat's own `active` flag in `chats_repo`.
The use case: an astro-trip ends and every enabled chat should go quiet at once, without visiting each one to run
`/disable`, and *without* losing which chats were enabled — `/resume` brings back exactly that set. `/disable` is
still the right tool for permanently removing one specific chat from monitoring; `/pause` is a temporary,
all-chats-at-once switch. Pausing only short-circuits the message-triage handler — admin commands (including
`/resume` itself) are handled by a separate handler and are never affected.

### Admin commands

All commands are gated by `utils/admin.py`'s `@admin_only` decorator (silently ignores non-admin users), checking
`message.from_user.id` against `ADMIN_IDS`. Two different scopes:

- **`/enable`, `/disable`** — must be run *inside the target group chat*; they flip that chat's `active` flag in
  `chats_repo`. There is no other way to target a chat, since the command itself carries no chat-id argument.
- **`/pause`, `/resume`, `/event [<text>]`, `/context [<text>]`, `/status`, `/stats`** — global in scope (not tied
  to whichever chat the command was typed in), so they work the same whether run in a group or in a private chat
  with the bot. Running them in a private DM with the bot is recommended to avoid dumping long context text into
  a group.
  - `/pause` sets the global kill switch (see above); `/resume` clears it.
  - `/event` with no argument shows the current trip context; `/event <text>` replaces it.
  - `/context` with no argument shows the persistent project context; `/context <text>` replaces it.
  - `/status` shows the global pause state, per known chat whether it's active, plus the current trip context
    summary.
  - `/stats` shows aggregate counts: total questions answered, total users seen, questions per chat.

`/event` and `/context` are deliberately two separate, independently-updatable pieces of context (see
`database/context_repo.py`) rather than one blob:
- **Project context** (`/context`) is evergreen — how registration generally works, what the community/format is,
  general rules — and rarely changes.
- **Trip context** (`/event`) is specific to whichever astro-trip is currently open for registration — date,
  meeting point, price, the registration link — and gets replaced before/at the start of every new trip's
  announcement.

Both are injected into every LLM call (step 5 above); splitting them means an organizer updating the trip details
for a new event doesn't have to retype the parts that never change.

`project_context` is seeded with `database/seed_data.py`'s `DEFAULT_PROJECT_CONTEXT` the first time `init_db()`
runs, so `/context` shows useful content (registration flow, ticketing, on-site rules — sourced from the
project's own FAQ/rules/howto pages) before any admin has ever touched it. The seed uses `INSERT OR IGNORE`, so
it never overwrites an admin's `/context` edit on a later restart — it only fills an empty row. `trip_context`
has no such seed (there's no sensible default for "the current trip"); it starts empty until the first `/event`.

### "/" command-menu scoping

`services/telegram_service.py::_register_bot_commands()` calls Telegram's `setMyCommands` with a different
`scope` per audience — purely a UI convenience (which commands Telegram suggests when a user types `/`), **not**
a permission check; `@admin_only` still gates execution regardless of what any menu shows. Three scopes, set once
at bot startup:

- `BotCommandScopeDefault()` (every chat with no more specific scope, i.e. every ordinary community chat) — an
  **empty** command list. There's no upside to suggesting `/pause`, `/stats`, etc. to a random participant, and
  the admin standing in that chat already knows `/enable`/`/disable` from `/help`.
- `BotCommandScopeChat(chat_id=ORGANIZERS_CHAT_ID)` — the full admin command list, since that's where admins
  actually run `/event`, `/context`, `/status`, `/stats`, `/pause`, `/resume`.
- `BotCommandScopeChat(chat_id=<admin_id>)` for every ID in `ADMIN_IDS` — the full list in each admin's own DM
  with the bot. This can fail per-admin with "chat not found" if that admin has never opened a DM with the bot
  yet (Telegram requires the chat to already exist); caught and logged, not fatal — the other scopes still work,
  and it self-heals the next time the bot restarts after that admin's first DM.

## LLM response contract

Single JSON object per call, always both keys present:

```json
{
  "relevant": true,
  "reply": "Текст ответа на русском"
}
```

When the message is not about the trip/project:

```json
{
  "relevant": false,
  "reply": ""
}
```

`reply` is always a string (never null/omitted) so `core/brain.py` can validate the shape without special-casing
the false branch; an empty string is simply never sent. `core/brain.py` treats `relevant: true` with an empty
`reply` as a non-answer (logged, not sent) — the model should not produce that combination given the prompt, but
the handler doesn't trust it blindly.

## Database (SQLite)

`data/support_bot.db`, opened with `check_same_thread=False` (telebot runs handlers on multiple threads) and
`PRAGMA journal_mode=WAL` / `busy_timeout=5000`, same as the sibling repos.

- **`users`** — `telegram_id` (PK), `username`, `first_name`, `last_name`, `profile_link`, `first_seen_at`,
  `last_seen_at`, `questions_count` (`users_repo.py`)
- **`chats`** — `chat_id` (PK), `title`, `active`, `enabled_at` (`chats_repo.py`)
- **`messages`** — `id`, `chat_id`, `user_id`, `message_id`, `text`, `is_reply_to_bot`, `relevant`, `reply_text`,
  `created_at` — every observed message in an active chat, whether or not the bot answered it (`messages_repo.py`)
- **`project_context`**, **`trip_context`** — single-row tables (`id = 1`), `text`, `updated_at`, `updated_by`
  (the admin's Telegram id) (`context_repo.py`); `project_context` is seeded with a default on first `init_db()`
  (`seed_data.py`)
- **`bot_state`** — single-row table (`id = 1`), `paused`, `updated_at`, `updated_by` — the global `/pause`/
  `/resume` switch (`bot_state_repo.py`)

## Configuration (.env)

Copy `.env.example` to `.env`. Required variables:

```env
BOT_TOKEN=            # Telegram bot token from @BotFather
ADMIN_IDS=            # Comma-separated Telegram user IDs allowed to run admin commands
ORGANIZERS_CHAT_ID=   # Chat ID the bot forwards every answered Q&A to
OPENAI_API_KEY=       # OpenAI API key — required when LLM_ENGINE=openai (the default)
```

`GROQ_API_KEY` becomes required instead of `OPENAI_API_KEY` if `LLM_ENGINE=groq`; either way, filling in *both*
keys turns the unused one into an automatic fallback (see "LLM engine" above) rather than a hard requirement.

Optional variables:

```env
LLM_ENGINE=              # "openai" or "groq" — primary provider (default: openai)
GROQ_API_KEY=            # Groq API key — required when LLM_ENGINE=groq, recommended as a fallback otherwise
OPENAI_MODEL=            # OpenAI model (default: gpt-4o-mini — cheap, since it runs on every single chat message)
GROQ_MODEL=              # Groq model (default: llama-3.3-70b-versatile)
USER_HISTORY_LIMIT=      # Past Q&A rows per user injected as LLM context (default: 5)
LOG_LEVEL=               # DEBUG/INFO/WARNING/ERROR (default: INFO)
```

There is deliberately no `ALLOWED_CHAT_IDS` whitelist: activation is entirely admin-driven via `/enable` per chat,
which is already gated by `ADMIN_IDS` — an extra whitelist would just duplicate that check.

## Telegram setup prerequisite

The bot must see *every* group message, not just mentions/replies/commands, in order to run the relevance check on
each one. This requires **disabling Privacy Mode** for the bot in BotFather (`/setprivacy` → Disabled) — otherwise
Telegram never delivers ordinary messages to the bot at all, and `/enable` would have nothing to act on. Same
prerequisite as `telegram-ai-bot`'s "observe block."

## Cost/latency note

Every message in an active chat costs one LLM call — this is intentional per the bot's spec (it must catch
questions that don't mention or reply to it), not an oversight. `OPENAI_MODEL` defaults to `gpt-4o-mini`
specifically because of this volume; do not default this to a larger/pricier model. If a chat turns out to be too
high-traffic for this to be affordable, the cheapest mitigation is a pre-filter in `message_handler.py` (e.g. skip
messages under some length, unless `is_reply_to_bot`) before spending an LLM call — not a smaller context per call.

## Development & Testing

- Python 3.11. Install deps with `pip install -r requirements.txt` (pyTelegramBotAPI, requests, python-dotenv).
- Run tests: `pytest tests/ -v`. `conftest.py` sets fake required env vars before import (since
  `config/settings.py` calls `require_env()` at import time).
- CI (`.github/workflows`) runs black (`--line-length 120`), isort (`--profile black`), pylint, then pytest —
  same toolchain as the sibling repos.

## Docker

`Dockerfile` + `docker-compose.yml`, same pattern as the sibling repos: the image bakes the application code in
(no source bind mount), and only `./data` (the SQLite file) is mounted as a volume so the DB survives a rebuild.
Local run: `cp .env.example .env`, fill it in, then `docker compose up -d --build`. `.dockerignore` keeps
`tests/`, `.env`, and dev-only files out of the image.

## systemd service (Raspberry Pi)

`telegram-support-bot.service` at the repo root is the production deployment path (the bot runs on a Raspberry
Pi), independent of Docker — same pattern as `telegram-bot.service`/`telegram-business-bot.service` in the
sibling repos: a plain venv + `python main.py` under systemd, `Restart=always`, no `EnvironmentFile=` (`.env` is
loaded by `python-dotenv` from the working directory, same as running it directly). The unit file hardcodes user
`mik` and `WorkingDirectory=/home/mik/telegram-support-ai-bot`, matching the actual Pi deployment path used for
the sibling bots — edit those two fields (and `Environment=`/`ExecStart=`) if the real path/user ever differs.
See README.md's "Running the Bot" for the full install/update steps.

## TODO / Roadmap

- **Pre-filter before the LLM call.** See "Cost/latency note" above — not yet needed, but the first thing to add
  if a chat's volume makes per-message LLM calls too expensive.
- **Group-admin self-service `/enable`.** Currently only users in `ADMIN_IDS` can toggle a chat; letting actual
  Telegram group admins do it themselves (checked via `getChatMember`) would remove the need to keep `ADMIN_IDS`
  in sync as new chats are added, at the cost of trusting Telegram's admin list instead of an explicit allowlist.
