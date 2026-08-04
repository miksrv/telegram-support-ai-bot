"""
Builds the classify+reply prompt, calls the LLM engine, and validates the
JSON response defensively — see CLAUDE.md's "LLM response contract".
"""

import json
import logging

from core.llm import llm_engine
from core.prompts import build_system_prompt

_FALLBACK_VERDICT = {"relevant": False, "reply": ""}


def _parse_verdict(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        logging.warning("LLM response was not valid JSON: %r", raw)
        return dict(_FALLBACK_VERDICT)

    relevant = data.get("relevant")
    reply = data.get("reply")

    if not isinstance(relevant, bool) or not isinstance(reply, str):
        logging.warning("LLM response had an unexpected shape: %r", data)
        return dict(_FALLBACK_VERDICT)

    return {"relevant": relevant, "reply": reply}


def classify_and_reply(
    message_text: str,
    project_context: str,
    trip_context: str,
    history: list,
    is_reply_to_bot: bool,
) -> dict:
    """
    Runs the single classify+reply LLM call for one message.

    Always returns {"relevant": bool, "reply": str} — a failed or malformed
    LLM call never crashes the caller and never fabricates a reply, it just
    yields {"relevant": False, "reply": ""}.
    """
    system_prompt = build_system_prompt(project_context, trip_context, history, is_reply_to_bot)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message_text},
    ]

    try:
        raw = llm_engine.complete(messages, temperature=0.3, max_tokens=500, json_mode=True)
    except Exception as e:  # pylint: disable=broad-except
        logging.error("LLM call failed — treating message as not relevant: %s", e)
        return dict(_FALLBACK_VERDICT)

    return _parse_verdict(raw)
