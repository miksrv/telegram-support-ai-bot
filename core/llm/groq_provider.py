import requests

from config.settings import GROQ_API_KEY, GROQ_MODEL
from core.llm.base import LLMProvider, LLMQuotaExceededError, build_session, is_quota_error, post_with_retry


class GroqProvider(LLMProvider):
    name = "groq"

    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self):
        self._session = build_session()
        self._headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }

    def complete(
        self,
        messages: list,
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool = True,
    ) -> str:
        payload = {
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Force valid JSON output at the API level instead of relying on prompt
        # instructions + brace-extraction fallback. All prompts already request
        # JSON and contain the word "json" (a Groq JSON-mode requirement).
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = post_with_retry(self._session, self.API_URL, self._headers, payload)
        except requests.exceptions.HTTPError as e:
            if is_quota_error(e.response):
                raise LLMQuotaExceededError(f"{self.name}: {e}") from e
            raise

        return response.json()["choices"][0]["message"]["content"].strip()
