# Telegram Support AI Bot

An AI-powered FAQ triage bot for Telegram group chats, built for the **"Смотри на звезды"**
([astro.miksoft.pro/stargazing](https://astro.miksoft.pro/stargazing)) astronomy community. When a stargazing trip
is announced, the same logistical questions — "how do I register?", "where's the meeting point?", "what do I
bring?" — get asked over and over in the community's group chats. This bot reads every message in the chats it's
turned on in, asks OpenAI whether it's a question about the trip, and if so answers it inline and flags it to the
organizers — without anyone having to babysit the chat.

## Table of Contents

- [How It Works](#how-it-works)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Running the Bot](#running-the-bot)
- [Telegram Setup](#telegram-setup)
- [Admin Commands](#admin-commands)
- [Answer Logic](#answer-logic)
- [Project Structure](#project-structure)
- [Development & Testing](#development--testing)
- [Related Projects](#related-projects)

---

## How It Works

1. An organizer adds the bot to a community group chat and runs `/enable` inside it.
2. Before (or right at) the start of a new trip's registration, an organizer privately messages the bot with
   `/event <details>` — where to meet, when, the registration link, price, etc. A separate, rarely-changed
   `/context <text>` holds the evergreen project info (how registration generally works, what the community is).
3. From then on, every text message posted in that chat is sent to OpenAI together with both contexts and asked:
   *is this a question about the trip, and if so, what's the answer?*
4. If the model says yes, the bot replies to that message directly in the chat **and** forwards a copy — with a
   link back to the original message and the asker's profile — to a private organizers' chat, so a human can
   step in, correct it, or just keep an eye on what's being asked.
5. If the model says no, the bot stays silent — but the message is still logged, so a later follow-up from the
   same person (even days later, even in a different chat) has conversational continuity.
6. If someone replies directly to one of the bot's own messages, it **always** answers — regardless of what the
   model would have otherwise decided — since a reply to the bot is unambiguously a continuation of that
   conversation.

Every user, question, and answer ends up in SQLite, so the organizers can mine it later for a real FAQ page, or to
follow up with specific attendees.

---

## Features

- **Silent relevance triage** — one OpenAI call per message decides both *is this on-topic* and *what's the
  answer*, so off-topic chatter never gets an unwanted reply
- **Two-tier context** — a rarely-changing project context plus a per-trip context that organizers swap out for
  each new astro-trip, without retyping what didn't change
- **Per-chat on/off switch** — `/enable`/`/disable`, run inside the chat itself, gates every chat independently
- **Always answers replies to the bot** — a reply to the bot's own message is treated as relevant no matter the
  topic, since it's clearly a continuation of a conversation the bot already started
- **Cross-chat user memory** — a user's recent questions and answers are pulled into the prompt even if they ask
  again in a different chat, or without replying to the bot's earlier message
- **Organizer visibility** — every answered question is forwarded to a private organizers' chat with a link to
  the original message and the asker's profile, so humans can double-check or jump in
- **Full audit trail** — every observed message (answered or not), every user, and every context change is kept
  in SQLite

---

## Prerequisites

- A Telegram bot token from [@BotFather](https://t.me/BotFather), with **Privacy Mode disabled** (see
  [Telegram Setup](#telegram-setup) — required for the bot to see every group message, not just mentions/replies)
- An [OpenAI API key](https://platform.openai.com/api-keys) (primary LLM provider), and optionally a
  [Groq API key](https://console.groq.com/keys) as an automatic fallback if OpenAI runs out of quota
- Your Telegram user ID and the organizers' chat ID (both from [@userinfobot](https://t.me/userinfobot))
- Python 3.11+, or Docker + Docker Compose

---

## Configuration

Copy the example environment file and fill in the values:

```bash
cp .env.example .env
```

```env
BOT_TOKEN=your_bot_token_here
ADMIN_IDS=123456789,987654321
ORGANIZERS_CHAT_ID=-1001234567890
LLM_ENGINE=openai
OPENAI_API_KEY=your_openai_api_key_here
GROQ_API_KEY=your_groq_api_key_here
LOG_LEVEL=INFO
```

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `ADMIN_IDS` | Comma-separated Telegram user IDs allowed to run admin commands |
| `ORGANIZERS_CHAT_ID` | Chat ID every answered question is forwarded to |
| `LLM_ENGINE` | Primary LLM provider: `openai` or `groq` (default: `openai`) |
| `OPENAI_API_KEY` | OpenAI API key — required when `LLM_ENGINE=openai` |
| `GROQ_API_KEY` | Groq API key — required when `LLM_ENGINE=groq`; if filled in while OpenAI is primary, it's kept on standby and the bot automatically switches to it if OpenAI runs out of quota |
| `OPENAI_MODEL` | OpenAI model (default: `gpt-4o-mini` — deliberately cheap, since it runs on *every* chat message, not just triggered ones) |
| `GROQ_MODEL` | Groq model (default: `llama-3.3-70b-versatile`) |
| `USER_HISTORY_LIMIT` | Past Q&A rows per user injected as LLM context (default: `5`) |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` (default: `INFO`) |

---

## Running the Bot

**With Docker (recommended for local testing):**

```bash
cp .env.example .env   # then edit it
docker compose up -d --build
docker compose logs -f
```

The SQLite database is persisted to `./data` on the host via a bind-mounted volume, so it survives image rebuilds.
The application code itself is baked into the image — edit-and-rebuild with `docker compose up -d --build` after
code changes, there's no live source mount.

**Without Docker:**

```bash
python -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env   # then edit it
python main.py
```

> A systemd `.service` unit for a Raspberry Pi/VPS deployment will be added once the bot has a stable first
> version — see `telegram-ai-bot`/`telegram-business-ai-bot` for the pattern this project will likely follow.

---

## Telegram Setup

1. Create the bot with [@BotFather](https://t.me/BotFather) and grab its token.
2. **Disable Privacy Mode**: BotFather → your bot → *Bot Settings* → *Group Privacy* → **Turn off**. Without this,
   Telegram only forwards messages that mention the bot or reply to it — the bot would never see the ordinary
   questions it's meant to catch.
3. Add the bot to each community group chat you want it active in.
4. Add the bot to (or create) a private organizers' chat, and put that chat's ID in `ORGANIZERS_CHAT_ID`.
5. In each community chat, have an admin (listed in `ADMIN_IDS`) run `/enable`.

---

## Admin Commands

All commands are restricted to Telegram user IDs listed in `ADMIN_IDS`; anyone else is silently ignored.

| Command | Where to run it | Description |
|---|---|---|
| `/enable` | Inside the target group chat | Turn the bot on for this chat |
| `/disable` | Inside the target group chat | Turn the bot off for this chat |
| `/event <text>` | Anywhere (DM recommended) | Set the current trip's context (date, meeting point, registration link, price, …) |
| `/event` | Anywhere | Show the current trip's context |
| `/context <text>` | Anywhere (DM recommended) | Set the evergreen project context (how the community/registration generally works) |
| `/context` | Anywhere | Show the current project context |
| `/status` | Anywhere | Show which chats are active, plus a summary of the current trip context |
| `/stats` | Anywhere | Show aggregate usage numbers: questions answered, users seen, per-chat breakdown |
| `/help` | Anywhere | List available commands (in Russian) |

**Example — setting up a new trip:**
```
/event Выезд 16 августа, встречаемся в 19:00 у ДК "Родина".
Регистрация: https://astro.miksoft.pro/stargazing
Возьмите тёплую одежду и коврик, оплата на месте.
```

---

## Answer Logic

For every text message in an active chat that isn't a command:

1. The bot checks whether the message is a reply to one of its own previous messages.
2. It looks up the sender's profile and their recent question/answer history (across all chats, not just this
   one) in SQLite.
3. One OpenAI call gets the persistent project context, the current trip context, that history, and the message,
   and returns a strict JSON verdict — see `CLAUDE.md` for the exact schema.
4. The message is saved to SQLite regardless of the verdict, so history keeps growing even for questions the bot
   didn't answer.
5. If the verdict says the message is relevant (or it's a reply to the bot, which is **always** treated as
   relevant): the bot replies in the chat, and a copy — with a link to the message and the asker's profile — is
   forwarded to the organizers' chat.
6. Otherwise, the bot stays silent.

---

## Project Structure

```
├── main.py                      # Entry point: init DB, init bot, start polling
├── config/settings.py           # Environment variables and constants
├── core/
│   ├── brain.py                 # Builds the classify+reply prompt, calls the LLM engine, validates the JSON response
│   ├── llm/                     # Pluggable LLM engine (interface shared with the sibling repos)
│   │   ├── engine.py            # LLMEngine: picks the active provider, single .complete() entry point
│   │   ├── base.py              # LLMProvider interface + shared HTTP session/retry helper
│   │   ├── openai_provider.py   # OpenAIProvider(LLMProvider) — primary provider
│   │   └── groq_provider.py     # GroqProvider(LLMProvider) — automatic fallback on quota exhaustion
│   └── prompts.py                # System prompt template: project context + trip context + user history
├── database/
│   ├── db.py                    # SQLite connection/schema init
│   ├── users_repo.py             # User profiles
│   ├── messages_repo.py          # Observed messages + verdicts/answers, per-user history lookup
│   ├── chats_repo.py             # Per-chat active/inactive flag
│   └── context_repo.py           # Persistent project context + current trip context
├── handlers/
│   ├── message_handler.py        # Main per-message triage flow
│   └── command_handler.py        # Admin commands
├── services/
│   ├── telegram_service.py       # Bot init, handler registration
│   └── forward_service.py        # Sends the Q&A card to the organizers chat
├── utils/
│   ├── identity.py                # Telegram user identity/profile-link extraction
│   └── admin.py                   # @admin_only decorator
└── data/                          # SQLite database (gitignored)
```

---

## Development & Testing

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v
```

`conftest.py` sets fake required env vars before any project module is imported, since `config/settings.py`
validates them at import time — same convention as the sibling repos.

---

## Related Projects

Two other Telegram bots by the same author, sharing the pluggable-LLM-engine pattern used here:

| Repository | What it does |
|---|---|
| [miksrv/telegram-ai-bot](https://github.com/miksrv/telegram-ai-bot) | TARS — a conversational AI companion for the same astronomy community, plus a CubeSat ground-station/star-chart interface over MQTT |
| [miksrv/telegram-business-ai-bot](https://github.com/miksrv/telegram-business-ai-bot) | An AI auto-reply assistant for Telegram Business accounts, with per-contact style learning |
