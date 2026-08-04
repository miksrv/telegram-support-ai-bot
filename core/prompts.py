"""
System prompt for the single classify+reply LLM call — see CLAUDE.md's
"LLM response contract" for the exact JSON shape this instructs the model to
produce.
"""

_HISTORY_HEADER = "Previous questions and answers from this user (most recent last):"

_REPLY_TO_BOT_INSTRUCTION = (
    "\nIMPORTANT: this message is a reply to one of the bot's own previous messages — treat it as "
    "ALWAYS relevant and produce an answer, regardless of topic, since the user is clearly continuing "
    "that conversation."
)


def _format_history(history: list) -> str:
    if not history:
        return ""

    lines = [_HISTORY_HEADER]
    for row in history:
        lines.append(f"- Q: {row['text']}\n  A: {row['reply_text']}")
    return "\n".join(lines)


def build_system_prompt(
    project_context: str,
    trip_context: str,
    history: list,
    is_reply_to_bot: bool,
) -> str:
    project_block = f"\nProject context:\n{project_context}\n" if project_context else ""
    trip_block = f"\nCurrent trip context:\n{trip_context}\n" if trip_context else ""
    history_block = f"\n{_format_history(history)}\n" if history else ""
    reply_instruction = _REPLY_TO_BOT_INSTRUCTION if is_reply_to_bot else ""

    return f"""You are an assistant for the "Смотри на звезды" (Stargazing) astronomy community's Telegram \
group chats. You monitor every message posted in the chat and decide whether it is a question about an \
upcoming astro-trip or the community/project in general that can be answered from the context below.
{project_block}{trip_block}{history_block}
Instructions:
- Decide whether the message is a question the context above can answer
- If relevant, write a concise, friendly, neutral answer in RUSSIAN, as if you were the event organizer's \
assistant — no persona, no jokes, no small talk
- Only use facts present in the project/trip context and the user's history above — never invent dates, \
prices, locations, or links that are not explicitly stated there
- If the context does not contain the answer, or the message is unrelated small talk/chatter, mark it as \
not relevant instead of guessing
{reply_instruction}

Respond with STRICT JSON only, exactly these two keys and nothing else — no markdown, no commentary:
{{"relevant": true or false, "reply": "answer in Russian, or an empty string if not relevant"}}"""


__all__ = ["build_system_prompt"]
